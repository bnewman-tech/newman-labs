select activity_id
from {{ ref('fact_houston_activity') }}
where
    (
        source_name = 'houston_311'
        and status != case when is_active then 'Open' else 'Closed' end
    )
    or (
        source_name = 'houston_emergency_center'
        and status != case when is_active then 'Active' else 'Inactive' end
    )
