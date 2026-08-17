select incident_id
from {{ ref('stg_houston_emergency_center__incident') }}
where (is_active and ended_at is not null)
   or (not is_active and ended_at is null)
   or ended_at < opened_at
   or last_seen_at < first_seen_at
   or agency not in ('F', 'P')
   or reported_unit_count <> unit_count
   or latitude not between -90 and 90
   or longitude not between -180 and 180
