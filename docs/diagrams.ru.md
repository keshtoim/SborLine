# СборЛайн — диаграммы системы

АИС учёта работы сотрудников сборочного цеха предприятия по производству мебельной фурнитуры: петель, шариковых направляющих и газлифтов. Диаграммы написаны на Mermaid и отрисовываются прямо на GitHub.

English version: [diagrams.en.md](diagrams.en.md)

1. [Архитектура системы](#1-архитектура-системы)
2. [ER-диаграмма](#2-er-диаграмма)
3. [Диаграмма классов (доменная модель)](#3-диаграмма-классов-доменная-модель)
4. [Диаграмма деятельности (жизненный цикл наряда)](#4-диаграмма-деятельности-жизненный-цикл-наряда)
5. [Диаграмма прецедентов (карта прецедентов)](#5-диаграмма-прецедентов-карта-прецедентов)

## 1. Архитектура системы

Настольное приложение из трёх слоёв, собранное PyInstaller в один `SborLine.exe`. Интерфейс обращается к данным только через слой бизнес-логики: там проверяются правила (разряд, допуск, остаток по наряду) и пишется журнал действий.

```mermaid
flowchart TB
    user(("Пользователь"))

    subgraph exe["SborLine.exe — PyInstaller, один файл"]
        direction TB
        run["run.py → app.main()"]

        subgraph ui["Слой представления — sborline/ui, PySide6"]
            login["LoginDialog<br/>вход по логину и паролю"]
            mw["MainWindow<br/>навигация по ролям"]
            pages["Страницы<br/>Сводка · Наряды · Табель · Ведомость<br/>Справочники · Пользователи · Журнал"]
            dialogs["Диалоги<br/>наряд · отчёт · сотрудник<br/>допуск · карточка сотрудника"]
            qss["style.qss"]
        end

        subgraph logic["Слой бизнес-логики"]
            services["services.py<br/>правила и расчёты<br/>ValidationError"]
            auth["auth.py<br/>PBKDF2-SHA256"]
            export["export.py<br/>выгрузка в Excel, openpyxl"]
            workcal["workcal.py<br/>производственный календарь"]
            seed["seed.py<br/>демо-данные"]
        end

        subgraph data["Слой данных"]
            db["db.py<br/>подключение, схема, миграция"]
            schema["schema.sql<br/>таблицы и представления<br/>v_route_rates · v_result_earnings"]
        end
    end

    sqlite[("SQLite<br/>%APPDATA%/SborLine/sborline.db")]
    xlsx[/"Ведомость .xlsx"/]

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

## 2. ER-диаграмма

Схема в третьей нормальной форме. Производные величины (расценка, заработок, процент выполнения нормы) не хранятся, а считаются в представлениях `v_route_rates` и `v_result_earnings`.

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
        text name UK "Участок"
    }
    positions {
        int  id PK
        text name UK "Должность"
    }
    grades {
        int     grade PK "Разряд 1-6"
        decimal hourly_rate "Часовая ставка"
    }
    employees {
        int  id PK
        text personnel_number UK "Табельный номер"
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
        text article UK "Артикул"
        text name
    }
    operations {
        int  id PK
        text code UK
        text name
        int  required_grade FK
        int  requires_permit "1 — нужен допуск"
    }
    employee_permits {
        int  id PK
        int  employee_id FK
        int  operation_id FK
        date valid_until "Срок действия"
    }
    bonus_settings {
        int     id PK "всегда 1"
        decimal threshold "Порог нормы, %"
        decimal per_pct "Премия за 1% сверх порога"
        decimal cap "Максимум, %"
    }
    product_operations {
        int     product_id PK, FK
        int     operation_id PK, FK
        int     seq_no "Порядок в маршруте"
        decimal norm_minutes "Норма времени"
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
        text number UK "Номер наряда"
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

    sections           ||--o{ employees          : "включает"
    positions          ||--o{ employees          : "занимают"
    grades             ||--o{ employees          : "имеют"
    grades             ||--o{ operations         : "требуется для"
    products           ||--o{ product_operations : "маршрут"
    operations         ||--o{ product_operations : "входит в"
    product_operations ||--o{ work_orders        : "выполняется по"
    employees          ||--o{ work_orders        : "получает"
    order_statuses     ||--o{ work_orders        : "статус"
    users              ||--o{ work_orders        : "выдал"
    work_orders        ||--o{ work_results       : "отчёты"
    defect_reasons     |o--o{ work_results       : "причина брака"
    users              |o--o{ work_results       : "принял"
    employees          ||--o{ timesheet          : "табель"
    shifts             |o--o{ timesheet          : "смена"
    absence_types      ||--o{ timesheet          : "код явки"
    roles              ||--o{ users              : "роль"
    employees          |o--o| users              : "учётка"
    users              |o--o{ audit_log          : "действия"
    employees          ||--o{ employee_permits   : "допуски"
    operations         ||--o{ employee_permits   : "требует допуска"
```

## 3. Диаграмма классов (доменная модель)

Понятия предметной области и правила, которые за ними закреплены. «Строка ведомости» не хранится: она собирается из табеля, отчётов и условий премирования на каждый расчётный период.

```mermaid
classDiagram
    direction LR

    class Section["Участок"] {
        +int id
        +str name
    }
    class Position["Должность"] {
        +int id
        +str name
    }
    class Grade["Разряд"] {
        +int grade
        +decimal hourly_rate
    }
    class Employee["Сотрудник"] {
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
    class Product["Изделие"] {
        +int id
        +str article
        +str name
    }
    class Operation["Операция"] {
        +int id
        +str code
        +str name
        +bool requires_permit
    }
    class RouteStep["Шаг техмаршрута"] {
        +int seq_no
        +decimal norm_minutes
        +piece_rate() decimal
    }
    class Permit["Допуск"] {
        +date valid_until
        +state(today) str
        +extend() date
    }
    class WorkOrder["Наряд"] {
        +str number
        +date issue_date
        +int planned_qty
        +remaining() int
        +add_result(good, defect, reason)
        +accept()
    }
    class OrderStatus["Статус наряда"] {
        <<enumeration>>
        ВЫДАН
        В_РАБОТЕ
        ВЫПОЛНЕН
        ПРИНЯТ
    }
    class WorkResult["Отчёт о выполнении"] {
        +date report_date
        +int qty_good
        +int qty_defect
        +norm_hours() decimal
        +earned() decimal
    }
    class DefectReason["Причина брака"] {
        +int id
        +str name
    }
    class TimesheetEntry["Запись табеля"] {
        +date work_date
        +decimal hours_worked
    }
    class AbsenceType["Код явки"] {
        <<enumeration>>
        Я_явка
        Б_больничный
        О_отпуск
        П_прогул
        В_выходной
    }
    class Shift["Смена"] {
        +str name
        +time start_time
        +time end_time
    }
    class BonusSettings["Условия премирования"] {
        +decimal threshold
        +decimal per_pct
        +decimal cap
        +calc_bonus(pct, earned, truancy) decimal
    }
    class PayrollLine["Строка ведомости"] {
        <<вычисляемая>>
        +decimal hours
        +decimal norm_hours
        +decimal pct
        +decimal earned
        +decimal bonus
        +decimal total
    }
    class User["Пользователь"] {
        +str login
        +str password_hash
        +bool is_active
        +authenticate(password) bool
    }
    class Role["Роль"] {
        <<enumeration>>
        АДМИНИСТРАТОР
        МАСТЕР
        СБОРЩИК
        БУХГАЛТЕР
    }
    class AuditEntry["Запись журнала"] {
        +datetime ts
        +str action
        +str entity
        +int entity_id
        +str details
    }

    Section "1" --> "*" Employee : включает
    Position "1" --> "*" Employee : занимают
    Grade "1" --> "*" Employee : разряд
    Grade "1" --> "*" Operation : требуемый разряд
    Product "1" *-- "*" RouteStep : техмаршрут
    Operation "1" --> "*" RouteStep
    Employee "1" *-- "*" Permit : допуски
    Operation "1" --> "*" Permit
    RouteStep "1" --> "*" WorkOrder : выполняется по
    Employee "1" --> "*" WorkOrder : исполнитель
    WorkOrder --> OrderStatus
    WorkOrder "1" *-- "*" WorkResult : отчёты
    DefectReason "0..1" --> "*" WorkResult
    Employee "1" *-- "*" TimesheetEntry : табель
    TimesheetEntry --> AbsenceType
    Shift "0..1" --> "*" TimesheetEntry
    User --> Role
    Employee "0..1" -- "0..1" User : учётная запись
    User "1" --> "*" WorkOrder : выдал
    User "1" --> "*" AuditEntry : действия
    PayrollLine ..> Employee
    PayrollLine ..> TimesheetEntry
    PayrollLine ..> WorkResult
    PayrollLine ..> BonusSettings
```

## 4. Диаграмма деятельности (жизненный цикл наряда)

Наряд — основной документ системы: от выдачи до попадания выработки в ведомость. Полосы показывают, кто выполняет каждый шаг.

```mermaid
flowchart TD
    start((Начало))
    finish((Конец))

    subgraph master["Мастер участка"]
        A["Открыть «Новый наряд»"]
        B["Выбрать сотрудника, изделие,<br/>операцию и количество"]
        P["Оформить допуск<br/>в справочнике «Допуски»"]
        M["Проверить выполненную работу"]
        N["Нажать «Принять»"]
    end

    subgraph worker["Сборщик"]
        G["Выполнить операцию"]
        H["Отчитаться: годные, брак,<br/>причина брака"]
    end

    subgraph system["Система"]
        C{"Разряд сотрудника<br/>не ниже требуемого?"}
        D{"Операция требует<br/>допуска?"}
        D2{"Есть действующий<br/>допуск?"}
        E1["Ошибка: выбрать<br/>другого исполнителя"]
        E2["Ошибка: нет<br/>действующего допуска"]
        F["Наряд создан, статус «Выдан»<br/>запись в журнал"]
        I{"Отчёт корректен?<br/>годные ≤ остатка,<br/>при браке есть причина"}
        E3["Ошибка в диалоге отчёта"]
        J{"Сдан весь объём?"}
        K["Статус «В работе»"]
        L["Статус «Выполнен»<br/>сигнал на сводке"]
        O["Статус «Принят»<br/>выработка в ведомости и премии"]
    end

    start --> A --> B --> C
    C -- нет --> E1 --> B
    C -- да --> D
    D -- нет --> F
    D -- да --> D2
    D2 -- да --> F
    D2 -- нет --> E2 --> P --> B
    F --> G --> H --> I
    I -- нет --> E3 --> H
    I -- да --> J
    J -- нет --> K --> G
    J -- да --> L --> M --> N --> O --> finish
```

Те же переходы в виде диаграммы состояний наряда:

```mermaid
stateDiagram-v2
    state "Выдан" as issued
    state "В работе" as progress
    state "Выполнен" as done
    state "Принят" as accepted

    [*] --> issued : мастер выдал наряд
    issued --> progress : отчёт, сдана часть объёма
    issued --> done : отчёт, сдан весь объём
    progress --> progress : очередной отчёт
    progress --> done : сдан остаток
    done --> accepted : мастер или ОТК принял
    accepted --> [*]
```

## 5. Диаграмма прецедентов (карта прецедентов)

Четыре роли и доступные им функции. Вход в систему нужен всем ролям. Связи «include» обязательны (выдача наряда всегда проверяет разряд и допуск), связи «extend» необязательны.

```mermaid
flowchart LR
    master["Мастер участка"]
    worker["Сборщик"]
    buh["Бухгалтер"]
    admin["Администратор"]

    subgraph sys["АИС «СборЛайн»"]
        direction TB
        uc_login(["Войти в систему"])
        uc_dash(["Смотреть сводку цеха"])
        uc_order(["Выдать наряд"])
        uc_check(["Проверить разряд и допуск"])
        uc_report(["Отчитаться о выполнении наряда"])
        uc_accept(["Принять выполненный наряд"])
        uc_ts(["Вести табель"])
        uc_pay(["Сформировать ведомость заработка"])
        uc_bonus(["Рассчитать премию"])
        uc_card(["Открыть карточку сотрудника"])
        uc_xlsx(["Выгрузить ведомость в Excel"])
        uc_my(["Смотреть свои наряды и заработок"])
        uc_permit(["Оформить или продлить допуск"])
        uc_staff(["Вести справочник сотрудников"])
        uc_rates(["Настроить тарифы и премирование"])
        uc_users(["Смотреть пользователей"])
        uc_audit(["Смотреть журнал действий"])
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
