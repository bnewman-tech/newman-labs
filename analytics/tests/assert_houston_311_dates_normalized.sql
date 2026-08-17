select case_number
from {{ ref('stg_houston_311__request') }}
where due_at <= timestamp with time zone '1900-01-02 00:00:00+00'
   or closed_at <= timestamp with time zone '1900-01-02 00:00:00+00'
