# SborLine — System Diagrams

Automated information system for tracking the work of assembly shop employees. The diagrams are written in Mermaid and render directly on GitHub.

Русская версия: [diagrams.ru.md](diagrams.ru.md)

1. [System Architecture](#1-system-architecture)
2. [ER Diagram](#2-er-diagram)
3. [Class Diagram (Domain Model)](#3-class-diagram-domain-model)
4. [Activity Diagram (Work Order Lifecycle)](#4-activity-diagram-work-order-lifecycle)
5. [Use Case Diagram](#5-use-case-diagram)

## 1. System Architecture

A three-layer desktop application packaged by PyInstaller into a single `SborLine.exe`. The UI reaches the data only through the business layer, which enforces the rules (grade, permit, remaining quantity) and writes the audit log.

```mermaid
flowchart TB
    user(("User"))

    subgraph exe["SborLine.exe — PyInstaller, one file"]
        direction TB
        run["run.py → app.main()"]

        subgraph ui["Presentation layer — sborline/ui, PySide6"]
            login["LoginDialog<br/>login and password"]
            mw["MainWindow<br/>role-based navigation"]
            pages["Pages<br/>Dashboard · Work orders · Timesheet · Payroll<br/>Reference data · Users · Audit log"]
            dialogs["Dialogs<br/>work order · report · employee<br/>permit · employee card"]
            qss["style.qss"]
        end

        subgraph logic["Business layer"]
            services["services.py<br/>rules and calculations<br/>ValidationError"]
            auth["auth.py<br/>PBKDF2-SHA256"]
            export["export.py<br/>Excel export, openpyxl"]
            workcal["workcal.py<br/>working calendar"]
            seed["seed.py<br/>demo data"]
        end

        subgraph data["Data layer"]
            db["db.py<br/>connection, schema, migration"]
            schema["schema.sql<br/>tables and views<br/>v_route_rates · v_result_earnings"]
        end
    end

    sqlite[("SQLite<br/>%APPDATA%/SborLine/sborline.db")]
    xlsx[/"Payroll .xlsx"/]

    user --> login
    run --> login
    run --> mw
    login --> auth
    mw --> pages
    pages --> dialogs
    qss -.-> mw
    pages --> services
    dialogs --> services
    pages --> export
    export --> xlsx
    services --> workcal
    seed --> workcal
    services --> db
    auth --> db
    seed --> db
    db --> schema
    db <--> sqlite
```

## 2. ER Diagram

The schema is in third normal form. Derived values (piece rate, earnings, norm fulfilment) are not stored: the `v_route_rates` and `v_result_earnings` views compute them.

```mermaid
---
config:
  layout: elk
  elk:
    mergeEdges: false
    nodePlacementStrategy: NETWORK_SIMPLEX
---
erDiagram
    sections {
        int  id PK
        text name UK "Shop section"
    }
    positions {
        int  id PK
        text name UK "Job title"
    }
    grades {
        int     grade PK "Skill grade 1-6"
        decimal hourly_rate "Hourly rate"
    }
    employees {
        int  id PK
        text personnel_number UK "Personnel number"
        text last_name
        text first_name
        text middle_name
        int  position_id FK
        int  section_id FK
        int  grade FK
        date hire_date
        date dismissal_date
    }
    products {
        int  id PK
        text article UK "Part number"
        text name
    }
    operations {
        int  id PK
        text code UK
        text name
        int  required_grade FK
        int  requires_permit "1 = permit required"
    }
    employee_permits {
        int  id PK
        int  employee_id FK
        int  operation_id FK
        date valid_until "Expiry date"
    }
    bonus_settings {
        int     id PK "always 1"
        decimal threshold "Norm threshold, %"
        decimal per_pct "Bonus per 1% above threshold"
        decimal cap "Maximum, %"
    }
    product_operations {
        int     product_id PK, FK
        int     operation_id PK, FK
        int     seq_no "Step in the route"
        decimal norm_minutes "Standard time"
    }
    shifts {
        int  id PK
        text name UK
        time start_time
        time end_time
    }
    absence_types {
        text code PK "Я, Б, О, П, В"
        text name
    }
    order_statuses {
        int  id PK
        text name UK
    }
    defect_reasons {
        int  id PK
        text name UK
    }
    roles {
        int  id PK
        text name UK
    }
    users {
        int  id PK
        text login UK
        text password_hash
        int  role_id FK
        int  employee_id FK, UK
        int  is_active
    }
    timesheet {
        int     id PK
        int     employee_id FK
        date    work_date
        int     shift_id FK
        text    absence_code FK
        decimal hours_worked
    }
    work_orders {
        int  id PK
        text number UK "Work order number"
        date issue_date
        int  employee_id FK
        int  product_id FK
        int  operation_id FK
        int  planned_qty
        int  status_id FK
        int  issued_by FK
    }
    work_results {
        int  id PK
        int  work_order_id FK
        date report_date
        int  qty_good
        int  qty_defect
        int  defect_reason_id FK
        int  accepted_by FK
    }
    audit_log {
        int      id PK
        int      user_id FK
        datetime ts
        text     action
        text     entity
        int      entity_id
        text     details
    }

    sections           ||--o{ employees          : "includes"
    positions          ||--o{ employees          : "held by"
    grades             ||--o{ employees          : "assigned to"
    grades             ||--o{ operations         : "required for"
    products           ||--o{ product_operations : "route"
    operations         ||--o{ product_operations : "part of"
    product_operations ||--o{ work_orders        : "performed as"
    employees          ||--o{ work_orders        : "receives"
    order_statuses     ||--o{ work_orders        : "status"
    users              ||--o{ work_orders        : "issued"
    work_orders        ||--o{ work_results       : "reports"
    defect_reasons     |o--o{ work_results       : "defect reason"
    users              |o--o{ work_results       : "accepted"
    employees          ||--o{ timesheet          : "timesheet"
    shifts             |o--o{ timesheet          : "shift"
    absence_types      ||--o{ timesheet          : "attendance code"
    roles              ||--o{ users              : "role"
    employees          |o--o| users              : "account"
    users              |o--o{ audit_log          : "actions"
    employees          ||--o{ employee_permits   : "permits"
    operations         ||--o{ employee_permits   : "requires permit"
```

Attendance codes follow the Russian timesheet convention: Я — present, Б — sick leave, О — vacation, П — truancy, В — day off.

## 3. Class Diagram (Domain Model)

Domain concepts and the rules attached to them. A payroll line is not stored: it is assembled for each pay period from the timesheet, work reports and bonus settings.

```mermaid
classDiagram
    direction LR

    class Section {
        +int id
        +str name
    }
    class Position {
        +int id
        +str name
    }
    class Grade {
        +int grade
        +decimal hourly_rate
    }
    class Employee {
        +int id
        +str personnel_number
        +str last_name
        +str first_name
        +str middle_name
        +date hire_date
        +date dismissal_date
        +short_name() str
        +is_working() bool
    }
    class Product {
        +int id
        +str article
        +str name
    }
    class Operation {
        +int id
        +str code
        +str name
        +bool requires_permit
    }
    class RouteStep {
        +int seq_no
        +decimal norm_minutes
        +piece_rate() decimal
    }
    class Permit {
        +date valid_until
        +state(today) str
        +extend() date
    }
    class WorkOrder {
        +str number
        +date issue_date
        +int planned_qty
        +remaining() int
        +add_result(good, defect, reason)
        +accept()
    }
    class OrderStatus {
        <<enumeration>>
        ISSUED
        IN_PROGRESS
        DONE
        ACCEPTED
    }
    class WorkResult {
        +date report_date
        +int qty_good
        +int qty_defect
        +norm_hours() decimal
        +earned() decimal
    }
    class DefectReason {
        +int id
        +str name
    }
    class TimesheetEntry {
        +date work_date
        +decimal hours_worked
    }
    class AbsenceType {
        <<enumeration>>
        PRESENT
        SICK_LEAVE
        VACATION
        TRUANCY
        DAY_OFF
    }
    class Shift {
        +str name
        +time start_time
        +time end_time
    }
    class BonusSettings {
        +decimal threshold
        +decimal per_pct
        +decimal cap
        +calc_bonus(pct, earned, truancy) decimal
    }
    class PayrollLine {
        <<computed>>
        +decimal hours
        +decimal norm_hours
        +decimal pct
        +decimal earned
        +decimal bonus
        +decimal total
    }
    class User {
        +str login
        +str password_hash
        +bool is_active
        +authenticate(password) bool
    }
    class Role {
        <<enumeration>>
        ADMIN
        MASTER
        WORKER
        ACCOUNTANT
    }
    class AuditEntry {
        +datetime ts
        +str action
        +str entity
        +int entity_id
        +str details
    }

    Section "1" --> "*" Employee : includes
    Position "1" --> "*" Employee : held by
    Grade "1" --> "*" Employee : grade
    Grade "1" --> "*" Operation : required grade
    Product "1" *-- "*" RouteStep : route
    Operation "1" --> "*" RouteStep
    Employee "1" *-- "*" Permit : permits
    Operation "1" --> "*" Permit
    RouteStep "1" --> "*" WorkOrder : performed as
    Employee "1" --> "*" WorkOrder : assignee
    WorkOrder --> OrderStatus
    WorkOrder "1" *-- "*" WorkResult : reports
    DefectReason "0..1" --> "*" WorkResult
    Employee "1" *-- "*" TimesheetEntry : timesheet
    TimesheetEntry --> AbsenceType
    Shift "0..1" --> "*" TimesheetEntry
    User --> Role
    Employee "0..1" -- "0..1" User : account
    User "1" --> "*" WorkOrder : issued
    User "1" --> "*" AuditEntry : actions
    PayrollLine ..> Employee
    PayrollLine ..> TimesheetEntry
    PayrollLine ..> WorkResult
    PayrollLine ..> BonusSettings
```

## 4. Activity Diagram (Work Order Lifecycle)

The work order is the system's core document, from issue until its output reaches the payroll. Swimlanes show who performs each step.

```mermaid
flowchart TD
    start((Start))
    finish((End))

    subgraph master["Shop master"]
        A["Open “New work order”"]
        B["Choose employee, product,<br/>operation and quantity"]
        P["Grant a permit<br/>in “Permits”"]
        M["Inspect the finished work"]
        N["Click “Accept”"]
    end

    subgraph worker["Assembler"]
        G["Perform the operation"]
        H["Report: good units, defects,<br/>defect reason"]
    end

    subgraph system["System"]
        C{"Employee grade<br/>meets the requirement?"}
        D{"Operation requires<br/>a permit?"}
        D2{"Valid permit<br/>on file?"}
        E1["Error: choose<br/>another assignee"]
        E2["Error: no<br/>valid permit"]
        F["Order created, status “Issued”<br/>audit log entry"]
        I{"Report valid?<br/>good ≤ remaining,<br/>defects have a reason"}
        E3["Error in the report dialog"]
        J{"Full quantity<br/>delivered?"}
        K["Status “In progress”"]
        L["Status “Done”<br/>dashboard alert"]
        O["Status “Accepted”<br/>output counted in payroll and bonus"]
    end

    start --> A --> B --> C
    C -- no --> E1 --> B
    C -- yes --> D
    D -- no --> F
    D -- yes --> D2
    D2 -- yes --> F
    D2 -- no --> E2 --> P --> B
    F --> G --> H --> I
    I -- no --> E3 --> H
    I -- yes --> J
    J -- no --> K --> G
    J -- yes --> L --> M --> N --> O --> finish
```

The same transitions as a work order state diagram:

```mermaid
stateDiagram-v2
    state "Issued" as issued
    state "In progress" as progress
    state "Done" as done
    state "Accepted" as accepted

    [*] --> issued : master issues the order
    issued --> progress : report, part delivered
    issued --> done : report, full quantity delivered
    progress --> progress : another report
    progress --> done : remainder delivered
    done --> accepted : master or QC accepts
    accepted --> [*]
```

## 5. Use Case Diagram

Four roles and the functions available to each. Every role has to log in. «include» links are mandatory (issuing an order always checks grade and permit); «extend» links are optional.

```mermaid
flowchart LR
    master["Shop master"]
    worker["Assembler"]
    buh["Accountant"]
    admin["Administrator"]

    subgraph sys["SborLine system"]
        direction TB
        uc_login(["Log in"])
        uc_dash(["View shop dashboard"])
        uc_order(["Issue work order"])
        uc_check(["Check grade and permit"])
        uc_report(["Report work done"])
        uc_accept(["Accept finished order"])
        uc_ts(["Keep timesheet"])
        uc_pay(["Build payroll"])
        uc_bonus(["Calculate bonus"])
        uc_card(["Open employee card"])
        uc_xlsx(["Export payroll to Excel"])
        uc_my(["View own orders and earnings"])
        uc_permit(["Grant or extend permit"])
        uc_staff(["Manage employee records"])
        uc_rates(["Configure rates and bonus"])
        uc_users(["View users"])
        uc_audit(["View audit log"])
    end

    master --- uc_login & uc_dash & uc_order & uc_report & uc_accept & uc_ts & uc_pay & uc_permit
    worker --- uc_login & uc_my & uc_report
    buh --- uc_login & uc_pay & uc_ts
    admin --- uc_login & uc_dash & uc_staff & uc_rates & uc_permit & uc_users & uc_audit

    uc_order -. "«include»" .-> uc_check
    uc_pay -. "«include»" .-> uc_bonus
    uc_card -. "«extend»" .-> uc_pay
    uc_xlsx -. "«extend»" .-> uc_pay

    classDef actor fill:#eef3f5,stroke:#1d282d,stroke-width:2px,font-weight:bold
    class master,worker,buh,admin actor
```
