with source as (
    select * from {{ source('houston_emergency_center', 'incident') }}
),

normalized as (
    select
        incident_id,
        source_incident_id,
        upper(nullif(trim(agency), '')) as agency,
        nullif(trim(address), '') as address,
        nullif(trim(cross_street), '') as cross_street,
        longitude,
        latitude,
        upper(nullif(trim(key_map), '')) as key_map,
        opened_at,
        nullif(trim(incident_type), '') as incident_type,
        nullif(trim(alarm_level), '') as alarm_level,
        reported_unit_count,
        units,
        cardinality(units) as unit_count,
        nullif(trim(combined_response), '') as combined_response,
        is_active,
        first_seen_at,
        last_seen_at,
        ended_at,
        ingested_at
    from source
)

select * from normalized
