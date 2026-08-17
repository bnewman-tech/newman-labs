# Houston Signal data attribution and use

Houston Signal is an independent Newman Labs project. It is not affiliated with,
endorsed by, or operated by the City of Houston, Houston 311, the Houston Fire
Department, the Houston Police Department, or OpenStreetMap.

## City of Houston sources

Houston Signal derives analytical records from two public City sources:

- [Houston 311 Recent Service Requests](https://mycity2.houstontx.gov/pubgis01/rest/services/311/Houston311_RecentServiceRequests/FeatureServer)
- [Houston Emergency Center Active Incidents](https://mycity2.houstontx.gov/pubgis01/rest/services/HEC/HEC_Active_Incidents/MapServer/0), including Fire and Police agency records

The City Open Data Portal's [Terms of Use](https://data.houstontx.gov/pages/terms-of-use)
require City of Houston attribution, a data-quality disclaimer, reasonable automated
access, and no implication of City endorsement. The ArcGIS layer does not publish a
separate license in its service metadata. Houston Signal therefore follows the portal's
attribution standard as a conservative product policy, names and links each source, and
does not imply that retained observations are a complete official history. This is not a
legal opinion.

## Location privacy

The database retains source coordinates to support governed transformations.
The public map does not return addresses, case numbers, or exact coordinates. It
rounds coordinates to two decimal places, approximately a one-kilometer cell in
Houston, and publishes counts for each cell. Public Houston Emergency Center output is
limited to agency counts and aggregate incident types.

## Map attribution and operations

The map visibly credits [OpenStreetMap contributors](https://www.openstreetmap.org/copyright).
The current low-traffic lab uses OpenStreetMap's standard raster tile service and
must comply with the [tile usage policy](https://operations.osmfoundation.org/policies/tiles/).
The browser supplies a normal referrer and honors cache headers; Newman Labs does
not prefetch, bulk-download, or provide offline tiles. Before traffic becomes
material, move to a provider or self-hosted tile service with an explicit service
agreement rather than depending on donated OpenStreetMap infrastructure.

## Public disclaimer

Houston Signal is exploratory analysis. It is not intended for emergency
response, real-time dispatch, damage verification, insurance decisions, public
safety decisions, or contact with affected residents. Source feeds can be
incomplete, delayed, corrected, or unavailable.
