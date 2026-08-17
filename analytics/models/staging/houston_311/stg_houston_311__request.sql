with source as (
    select * from {{ source('houston_311', 'request') }}
),

normalized as (
    select
        case_number,
        case_number_365,
        nullif(trim(status), '') as workflow_status,
        created_at,
        case
            when due_at > timestamp with time zone '1900-01-02 00:00:00+00'
                then due_at
        end as due_at,
        case
            when closed_at > timestamp with time zone '1900-01-02 00:00:00+00'
                then closed_at
        end as closed_at,
        nullif(trim(case_type), '') as case_type,
        upper(nullif(trim(key_map), '')) as key_map,
        nullif(trim(service_area), '') as service_area,
        upper(nullif(trim(council_district), '')) as council_district,
        nullif(trim(department), '') as department,
        nullif(trim(division), '') as division,
        latitude,
        longitude,
        first_seen_at,
        last_seen_at,
        ingested_at
    from source
)

select * from normalized
