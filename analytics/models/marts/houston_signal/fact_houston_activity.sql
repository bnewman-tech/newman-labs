with service_requests as (
    select
        '311:' || case_number as activity_id,
        'houston_311' as source_name,
        null::text as agency,
        '311 service request' as activity_kind,
        created_at as activity_at,
        closed_at,
        case when closed_at is null then 'Open' else 'Closed' end as status,
        workflow_status as source_status,
        case_type as activity_type,
        case
            when lower(case_type) similar to '%(water|sewer|drain|flood)%'
                then 'water and drainage'
            when lower(case_type) similar to '%(garbage|trash|recycl|container)%'
                then 'waste and recycling'
            when lower(case_type) similar to '%(traffic|street|pothole|signal|sidewalk)%'
                then 'streets and traffic'
            when lower(case_type) similar to '%(weed|property|building|code)%'
                then 'property and neighborhood'
            else 'other 311'
        end as activity_category,
        key_map,
        council_district,
        latitude,
        longitude,
        closed_at is null as is_active,
        null::integer as unit_count,
        first_seen_at,
        last_seen_at,
        ingested_at as source_refreshed_at
    from {{ ref('stg_houston_311__request') }}
),

emergency_incidents as (
    select
        'houston_emergency_center:' || incident_id as activity_id,
        'houston_emergency_center' as source_name,
        agency,
        'emergency incident' as activity_kind,
        opened_at as activity_at,
        ended_at as closed_at,
        case when is_active then 'Active' else 'Inactive' end as status,
        null::text as source_status,
        incident_type as activity_type,
        case
            when agency = 'F'
                and lower(incident_type) similar to '%(fire|smoke|alarm|gas|hazmat)%'
                then 'fire and alarm'
            when agency = 'F'
                and lower(incident_type) similar to '%(ems|patient|medical)%'
                then 'medical response'
            when agency = 'F'
                and lower(incident_type) similar to '%(vehicle|accident|pedestrian)%'
                then 'traffic incident'
            when agency = 'F' then 'other fire response'
            when agency = 'P' then 'police response'
            else 'other emergency response'
        end as activity_category,
        key_map,
        null::text as council_district,
        latitude,
        longitude,
        is_active,
        unit_count,
        first_seen_at,
        last_seen_at,
        ingested_at as source_refreshed_at
    from {{ ref('stg_houston_emergency_center__incident') }}
)

select * from service_requests
union all
select * from emergency_incidents
