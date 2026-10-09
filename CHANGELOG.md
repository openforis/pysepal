## v4.1.0 (2026-09-24)

### Feat

- **RightPanel**: add a footer slot below the scrolling sections (#1071)
- **RightPanel**: add a footer slot below the scrolling sections

### Fix

- **SepalMap**: make AOI layers follow the map theme (#1072)
- **SepalMap**: make AOI layers follow the map theme
- **MapApp**: keep disabled drawer controls from regaining pointer events

## v4.0.0 (2026-09-22)

### Feat

- **scripts**: screenshot, wait-js and repeatable clicks in browser_probe
- **demo**: add a Sentinel-1 radar layer to the map app
- **demo**: chart contexts demo and the measured resize rules (#1063)
- **demo**: chart contexts demo

### Fix

- **MapApp**: drop the object-form watchers on synced traits (#1068)
- **logger**: stop a local logging config from blinding caplog (#1059)
- **MapApp**: accept a bare widget as step or panel content
- **MapApp**: render step content widgets by iterating the list

## v4.0.0rc2 (2026-09-15)

### BREAKING CHANGE

- use_notifications() raises NotificationProviderError when no
NotificationProvider is mounted. Pass required=False from components that are
published for reuse and report feedback themselves.
- get_scoped_state, has_scoped_state and clear_scoped_state
are removed with pysepal.solara.ui_state. Use get_current_theme_state().
- the plain MapApp(...) constructor builds no language
selector; only MapApp.element(...) does. LocaleSelect loses selected_locale,
translator= and locales=; it carries value only.
- a catalogue leaf using {a.b}, {a[0]}, {a!r} or {a:spec} is
refused when the catalogue binds. pysepal.message.ms is removed; nothing in
pysepal read it.
- English that str.format cannot render now raises when the
catalogue binds. Every other locale falls back to English, so English that
cannot render leaves nothing to fall back to.
- AoiModel.METHODS entries carry "label_key" instead of "name";
AoiModel.CUSTOM and ADMIN are now "custom" and "admin"; AssetSelect.TYPES
values are catalogue keys; VectorField.column_base_items is a read-only
property; six functions that took a translated default now take None.
- LocaleState, use_locale, get_current_locale_state and
resolve_locale_state are removed. Use pysepal.i18n.current_locale() and
set_locale(). MapApp no longer accepts locale_state= and raises TypeError.

### Feat

- **demo**: a GEE AOI save/restore demo, and fix how the demos reach the notification bus (#1060)
- **demo**: add a GEE variant of the AOI save and restore demo
- **solara/notifications**: require a provider, with an opt-out for reuse
- **i18n**: one msg() lookup over a flat message catalogue (#1037)
- **i18n**: select plural forms with each locale's CLDR rules
- **demo**: translate every demo app, not only its outer shell
- **i18n**: make the locale reactive scope state
- **i18n**: add the message catalogue
- **solara/aoi**: restore an AOI selection from a serializable spec (#1031)
- **demo**: persist and restore the AOI in the GEE map app
- **demo**: add an AOI save and restore demo app
- **demo**: ship a sample AOI in every format the picker reads
- **solara/aoi**: restore AoiView from a persisted spec
- **solara/inputs**: seed the pickers from an externally set value
- **solara/aoi**: record the selection spec on every AoiResult
- **solara/aoi**: add AoiSpec, the serializable AOI selection
- **gee**: let asset exports set a pyramiding policy (#1043)
- **gee**: let asset exports set a pyramiding policy

### Fix

- **demo**: mount the notification bus where the Voila entrypoint can reach it
- **solara/aoi**: translate the missing-draw-control message and stop the docstring teaching inline alerts
- **solara/aoi**: refuse ambient Earth Engine credentials in every AOI method (#1057)
- **solara/aoi**: refuse ambient Earth Engine credentials in every AOI method
- **mapping**: unobserve the theme when a SepalMap closes (#1056)
- **sepalwidgets**: unobserve the theme toggle when a disclaimer tile closes
- **mapping**: unobserve the theme when a SepalMap closes
- **solara**: release the theme with its kernel, make the bus lock reentrant (#1054)
- **solara/notifications**: release publisher ownership with the idle check
- **solara/notifications**: log messages dropped without a provider
- **solara/notifications**: defer a subscriber's own publication
- **solara/notifications**: make the bus lock reentrant
- **mapping,inputs**: map background, zoom floor and input alignment (#1046)
- **inputs**: centre the inner icons of a dense field
- **solara/inputs**: make the asset select sync icon reload the assets
- **inputs**: keep prepended icons inside the field they belong to
- **sepalwidgets**: give the file picker one inset and a live stylesheet
- **mapping**: stop zooming out past a world that fills the viewport
- **mapping**: paint the map void in the map's own theme
- **solara**: merge the server assets once per process (#1050)
- **solara**: merge the server assets once per process
- **deps**: require ee-client 3.2.1 (#1052)
- **deps**: require ee-client 3.2.1
- **solara**: translate the Select AOI labels and drop the debug button
- **aoi**: copy the shared method list instead of stripping it
- **i18n**: close three gaps review found in catalogue validation
- **translator**: search sibling dicts past the first in search_key
- **solara/aoi**: clear the AOI layers by key, not by name
- **solara/aoi**: keep a caller-owned value on unmount
- **solara/session**: refuse a session-less interface under dev-auth connections
- **solara/session**: scope a dev-auth session per connection

### Refactor

- **solara/theme**: hold the theme in a solara kernel store
- **demo**: reshape the AOI buttons, keep save and restore in the AOI app only
- **i18n**: hold the locale in one Solara reactive per kernel
- **i18n**: accept only named placeholders in a message
- **i18n**: read pysepal's own messages with msg()
- **locale**: use one canonical locale matcher
- move the runtime scope primitives above pysepal.solara
- **solara**: drive the pickers and AOI restore from an editable draft
- **solara/inputs**: hold the admin cascade as one code tuple

## v4.0.0rc1 (2026-09-03)

### Fix

- **mapping**: keep the basemap order given by the caller (#1041)
- **mapping**: keep the basemap order given by the caller
- **mapping**: drive the CARTO backgrounds off a single API key (#1036)
- **mapping**: drive the CARTO backgrounds off a single API key
- **mapping**: make the background basemaps configurable (#1035)
- **mapping**: make the background basemaps configurable

## v4.0.0rc0 (2026-08-20)

### Feat

- **scripts**: add --click and --resize to browser_probe (#1020)
- **demos**: add a vector tile demo app
- browser-owned locale resolution for pysepal 4.0 (#1028)
- **sepalwidgets**: bind the selectors to the shared locale state
- **sepalwidgets**: resolve the locale in the browser
- **solara**: add scope-keyed locale state
- **solara**: run on local Earth Engine credentials under PYSEPAL_LOCAL_EE
- **solara**: render the admin panel from the typed session payloads
- **solara**: return read-only SessionInfo and SessionsOverview payloads
- **solara**: consume ee-client 4 and pysepal-api 0.3
- **solara**: drop the header gate from with_sepal_sessions
- **solara**: remove the headerless interface fallbacks
- **solara**: build one lazily-populated session per process
- **solara**: dispatch create_session on runtime topology
- **solara**: replace SOLARA_TEST with PYSEPAL_DEV_AUTH
- **solara**: resolve a session's credential source from runtime topology
- **solara**: publish one public surface for pysepal.solara
- delete the ~/.sepal-ui-config file and its readers
- **translator**: resolve locale without ~/.sepal-ui-config
- **frontend**: stop persisting the theme in ~/.sepal-ui-config
- **scripts**: deprecate writing the theme to ~/.sepal-ui-config
- **solara**: add a scope-keyed UI-state registry
- **mapping**: add add_raster_async and a warp_to_3857 option
- **mapping**: prepare rasters as cached COGs before serving tiles

### Fix

- **scripts**: read a task's state off the ee-client model, not by subscript
- **solara**: build SessionInfo under the scope lock
- refuse a session-less GEEInterface in a per-connection runtime
- **mapping**: refuse ambient Earth Engine credentials per connection
- **mapping**: opt out of localtileserver 1.0's prefix autodetection
- **sepalwidgets**: push panel updates into the child RightPanel
- **sepalwidgets**: stop the locale pick vanishing instead of persisting
- **solara**: detect a SEPAL sandbox from the SEPAL env var
- **solara**: serialise SessionManager construction against a split registry
- **solara**: pin solara and fail loudly when its private APIs move
- **solara**: refuse an explicit process scope in get_session_info
- **solara**: close the last two doors into the shared process session
- **solara**: make resolve_scope_id total against a broken kernel
- **solara**: serialize reopen_scope against cleanup_session
- **solara**: give each module_name its own SepalClient in one session
- **solara**: harden create_session against races and identity reuse
- **solara**: make session info helpers total instead of raising
- **mapping**: zoom add_raster to the raster, not to a tile
- **mapping**: require localtileserver 1.0 and key caches on their inputs
- **mapping**: cache prepared rasters on scratch, not in the user's home
- **mapping**: draw local rasters in the colours the caller asked for
- **mapping**: only prune foreign GDAL_DATA/PROJ_LIB, keep own-prefix paths (#1016)
- **mapping**: prune PROJ_DATA and compare prefixes as paths
- **mapping**: only prune foreign GDAL_DATA/PROJ_LIB, keep own-prefix paths

### Refactor

- **scripts**: remove the global-ee asset and task helpers
- drop emojis from UI text and log messages
- route every GEEInterface call through its session
- **scripts**: remove the gee asset helpers deprecated in 3.2.0
- drop the unused GEEInterface(use_sepal_headers=...) login
- **demos**: read the theme through get_current_theme_state
- **solara**: stop falling back to the process scope for theme state
- **solara**: put SessionManager on the shared ScopeRegistry
- **solara**: put the notification bus on the shared ScopeRegistry
- **solara**: put UI state on the shared ScopeRegistry
- **solara**: replace get_session_component with typed accessors
- **solara**: name the runtime scope scope_id everywhere
- **solara**: define the session errors in one module only
- remove the deprecated SepalClient compat shim
- drop the sepal_ui compatibility package
- **solara**: drop admin.py's duplicate session info helpers
- **solara**: drop theme state from SessionManager sessions
- **solara**: key theme state by runtime scope instead of the session
- **demos**: extract the solara demos into a checkout-only demo_apps/
- **mapping**: drop version directives and tighten the lazy imports
- **templates**: split solara_map_app app.py into component packages (#1022)
- **templates**: split solara_map_app app.py into component packages


- cap ipyvuetify below 3.0
- floor ee-client at 3.1.0 rather than an unreleased 4.0.0

## v3.8.1 (2026-07-30)

### Fix

- keep scratch files off NFS on SEPAL (#1021)
- keep scratch files off NFS on SEPAL

## v3.8.0 (2026-07-30)

### Feat

- **mapping**: PMTiles layers in LayersControl, and fix modal layering + the GEE event loop (#1018)
- **legend**: collapse the legend while the logger is open
- **mapping**: show and toggle PMTiles layers in LayersControl
- **legend**: optional detail text and layer selector for LegendComponent (#1015)

### Fix

- **solara**: fall back to headerless state when no session can exist
- **templates**: pass the session interfaces into the export panel
- **css**: renumber app layers below vuetify's modal baseline
- **templates**: schedule the map_app layer button on solara's loop
- **AssetSelect**: guard None from get_assets_async (#1013)
- **FileInput**: select_file must store string paths, not PosixPath (#1009)
- **gee**: init_ee no-ops when credentials are unavailable (#1012)

## v3.7.0 (2026-07-15)

### Feat

- **export**: add band selection to export dialog (#1001)
- **export**: add band/property selection to the export dialog
- add Voila AOI notebook entrypoint (#1006)
- support Voila runtime contexts (#1004)
- adopt pysepal-api 0.2.0 and ee-client 3.0.0 (agnostic auth) (#1003)

### Fix

- **voila**: align notification/markdown theme parity with Solara (#1007)
- **voila**: align notification/markdown theme parity with Solara
- **templates**: use EESession.from_default for the default session
- **gee**: close the EESession HTTP client on GEEInterface.close() (#1000)
- **aoi**: avoid 2M-edge dissolve in AOI bounds computation (#998)

### Refactor

- **notifications**: drive theme from ThemeState prop, drop DOM scan
- **css**: extract shared base.css, keep per-runtime overrides
- **legend**: use a persistent toggle bar to open and close

### Perf

- **mapping**: lazy-import the raster stack (add_raster only) (#999)

## v3.6.2 (2026-06-22)

### Fix

- **sepalwidgets**: read VectorField property names server-side to avoid pulling geometry (#997)

## v3.6.1 (2026-05-16)

## v3.6.0 (2026-05-15)

### Feat

- **solara/export**: Asset ID field + required/root/conflict checks (#989)
- **solara**: carry SEPAL visualization onto exported images (#986)
- **solara**: carry SEPAL visualization onto exported images

## v3.5.0 (2026-05-07)

### Feat

- **MapApp**: responsive bottom panel + fixes (#982)
- **MapApp,SepalMap**: reserve bottom-panel height in narrow mode
- **MapApp**: responsive bottom-panel layout for narrow viewports

### Fix

- **MapApp,SepalMap**: center on Y-axis with bottom inset, flip toggle tab geometry on narrow
- **Legend**: remove position transition so it tracks viewport instantly
- **MapApp**: keep narrow-mode right-panel rules in scoped style
- **MapApp,Legend**: move cross-component CSS out of scoped, dedupe panel height
- **aoi,assets**: fall back to GEE root when folder is None instead of literal "None"
- **Legend**: lift above bottom panel and hide during step dialogs
- **TaskButton**: bind disabled prop to v-btn

## v3.4.1 (2026-04-24)

### Feat

- **mapapp,rightpanel**: polish sidebar, right panel, and map shadows

### Fix

- **packaging**: ship all .vue templates in the wheel

## v3.4.0 (2026-04-24)

### Feat

- **solara**: add reusable export component for EE / Drive / SEPAL
- **aoi**: route input-component errors through the notification system
- **aoi**: wire up SHAPE/POINTS/ASSET methods and extract AdminLevelSelector
- **legend**: center legend location
- **notifications**: cancel toast type, themed styling, provider refactor
- **notifications**: add centralized notification system
- wire LegendComponent to Legend.vue via component_vue
- add Legend.vue template with gradient bar and discrete chips
- add LegendData dataclasses for reusable legend component
- add all-methods AOI demo template
- add input selector Solara components
- add AOI processors for shape, points, and asset methods
- add TaskButtonComponent for async task cancellation
- reintroduce geoman drawing tool as default
- update external URLs and references for openforis/pysepal (Phase 3) (#978)
- update external URLs and references for openforis/pysepal (Phase 3)

### Fix

- **mapapp**: default drawer to mini when not pinned on mount
- **theme**: correct theme_toggle deprecation version to 3.4.0
- **aoi**: reuse cleanup path for external clear
- **aoi**: close internal gee interface in admin flow
- **solara**: wire legend props and collapse callback
- **mapping**: derive map viewport from bounds/window for correct fit_bounds
- **aoi**: improved inline fallback when no NotificationProvider
- **MapApp**: layout desync with right panel and broken pin button
- prevent event loop mismatch and reuse session GEEInterface in AoiView
- widen AoiResult.feature_collection to ee.ComputedObject
- check for bounded geometries
- typo in async loop cancellation
- resolve session lifecycle bugs in Solara session management (#980)
- address PR review feedback
- resolve session lifecycle bugs in Solara session management
- use PurePosixPath for GEE asset IDs (#979)
- use PurePosixPath for GEE asset IDs to avoid backslashes on Windows

### Refactor

- **mapping**: drop legacy deprecations and tighten comments
- **templates**: migrate solara_map_app to theme_state
- **theme**: session-scoped ThemeState for Solara apps
- moved fileInput solara component to solara components folder

## v3.3.0 (2026-03-04)

### Feat

- rename package from sepal_ui to pysepal (Phase 2) (#975)
- update module_deploy for pysepal with dual-read config
- add sepal_ui backward-compatibility import shim

### Refactor

- fix remaining 'from sepal_ui import X' patterns missed by initial rename
- update module_factory welcome message to pysepal
- update notebook imports from sepal_ui to pysepal
- update template Python imports from sepal_ui to pysepal
- rename all test imports from sepal_ui to pysepal
- rename all internal imports from sepal_ui to pysepal
- update pysepal/__init__.py imports and remove old deprecation warning
- rename sepal_ui/ directory to pysepal/

## v3.2.0 (2026-02-16)

### Fix

- prepare sepal-ui deprecation notice for pysepal migration (#967)
- docstring rst

## v3.1.1 (2026-02-12)

### Fix

- **solara.aoi_view**: remove unused map_ param

## v3.1.0 (2026-02-11)

### Feat

- resolve copilot comments

### Refactor

- **aoi**: centralize FAO GAUL constants to eliminate duplication

## v3.0.1 (2026-01-31)

### Feat

- support AOI admin WFS fetch in AoiResult
- add init to module
- create Admin Select solara component
- autocenter on async operation
- use ee method to determine the credentials

### Fix

- **deps**: update pygaul and localtileserver for compatibility (#970)
- **docs**: update expected warning format for Python 3.12
- **aoi**: address review comments
- **deps**: update pygaul and localtileserver for compatibility
- fix gaul file lcoation
- typo

## v2.22.1 (2024-11-22)

### Fix

- revert to legacy draw control due to errors (#958)

## v2.22.0 (2024-11-21)

### Feat

- request assets in a separate thread (#954)

## v2.21.0 (2024-10-25)

### Feat

- add geoman drawing control (#951)

## v2.20.3 (2024-10-20)

### Fix

- https://github.com/openforis/sepal_ui/issues/893 (#948)

## v2.20.2 (2024-10-20)

### Fix

- merge
- closes #938 (#947)
- closes #938

## v2.20.1 (2024-09-20)

### Fix

- set chunk dict. closes #940 (#941)
- remove changelog. closes #917

### Refactor

- Change Translation menu icon (#939)
- remove changelog (#935)
- remove changelog from doctree

## v2.20.0 (2024-08-26)

### Feat

- draft async get assets (#934)
- limit the number of async tasks based on memory and earthengine rate limits
- fallback to sync call in case async fails
- draft async get assets

### Fix

- **planet.ver**: unpin planet version (#937)
- **planet.ver**: unpin planet version. see: https://github.com/openforis/sepal_ui/issues/920

### Refactor

- remove changelog

## v2.18.1 (2024-08-20)

### Refactor

- store initial assets in class variable (#932)
- store initial assets in class variable

## v2.18.0 (2024-08-06)

### Feat

- ignore act_unit test
- merge
- create entry point script to rename entry point ui notebooks
- Make a lazy loading of gee gdf..close #919. (#922)
- Make a lazy loading of gee gdf..close #919.
- make theme change interactive (#913)
- change badge alert hardc-ded color
- change badge alert hardc-ded color
- link sepal.color with v.theme
- make theme change interactive
- adapt to voila-sepal-ui template. #909 (#910)
- add fullscreen control as additional parameter to sepalmap
- link sepal.color with v.theme
- make theme change interactive
- adapt to voila-sepal-ui template. #909
- use earthengine OF fork when running test in sepal
- update gdal sepal version, mimic sepal venv creation
- update auth process
- **AssetSelect**: add info when there are not asset
- update gee auth process with project

### Fix

- pin planet version until #920 is fully fixed
- full_screen_menu
- set z-index on menus for fullscreen maps
- set menu z-index for fullscreen
- remove legacy brackets

### Refactor

- remove kaban project ftm
- install gdal as binary if we are in github actions by checking the path
- use the name of the folder as venv name, not the stem
- evaluate gdf in get_ipygeojson since this function is agnostic regarding gee-mode
- **aoi_model**: - set gdf when vector or geojson is set in method. - don't evaluate gdf in conditions to avoid request when using gee.
- add preffix param
- only do one call to gee
- round total bounds
- merge new theme
- remove hard-coded styles
- appbar icon
- merge main
- extend the length of the black lines to 100 chars (#916)
- extend the length of the black lines to 100 chars
- update gee auth process (#915)
- restore previous secrets
- customize default colors + remvoe unnecessary space
- merge gee_aut
- update gee auth process
- readabilitty
- **map_fullscreen**: simplify fullscreen method for maps
- remove hard-coded styles
- customize default colors + remvoe unnecessary space
- remove http_transport method on ee initialization. see #914
- **init_ee**: only initialize ee if there's no an authentication data already
- ony initialize ee when there's no a previous authentication
- expose errors on ee initialization
- update init_ee method to use project_id
- set new gee project folder structure

## v2.17.0 (2023-11-30)

### Feat

- Planet enhance (#896)
- mkdir on temp_path_factory obj
- **planet**: save credentials and authenticate from file
- update pip and install numpy beofre gdal
- add dummy changelog and version to panel_app template
- define arguments to changelog functions
- define arguments to changelog functions
- use local repository data to show changelog
- define methods to process and retrieve the changelog from remote repo
- set the view of the version manager for apps
- use cache on InputFile widget to improve loading times
-  use localtileserver as native deps (#835)
- add localtileserver in the deps

### Fix

- drop the changelog only rely on Github as we are building everything based on PRs
- merge from main
- fix rendered cells issue
- display a message at the top of the notebook while loading
- use Python 3.11 (#899)
- use Python 3.11
- **planet_model**: Fix #895. - Request quads and mosaics using authenticated session
- fix gdal isntlalation
- use the latest earthengine fork api from sepal
- typo
- **css**: revert render_cells css attributes that caused #893
- **decorator**: make debug mode true always
- fix js code issues on fontawesome removing code (#889)
- fix js code issues on fontawesome removing code
- use catch_error in loading_button (#879)
- use catch_error in loading_button
- stop overriding the default behavior of the footer (#880)
- missing install command
- run github tests with nox sessions
- stop overriding the default behavior of the ooter
- externalyse geometries management (#868)
- display a message at the top of the notebook while loading (#871)
- display a message at the top of the notebook while loading
- only test existence of mosaics (#872)
- only test existence of momsaics
- use sphinx<7 for the moment (#869)
- use sphinx<7 for the moment
- use pygaul/pygadm in admin selects
- display meaningfull message if the folder list is empty (#867)
- display meaningfull message if the folder list is empty
- don't change folder when new folder is parent of root.  (#863)
- don't change folder when new folder is parent of root. closes #862
- python 3.11 is more specific when dealing with glob specs
- add `self` to `catch_error` decorator (#856)
- check if the alert and btn exist in the parent object
- return alert to info state when reset
- add self to catch_error decorator
- typo variable name
- update planet mosaic list in tests (#853)
- update planet mosaic list in tests
- change default branch on docs. closes #846 (#847)
- change default branch on docs. closes #846
- closes #838. remove inline js comments (#840)
- closes #838. remove inline js comments
- add method to delete a folder and all its content (#793)
- make the function dry run by default
- [] is a mutable object
- split files by nesting level
- add method to delete a folder and all its content
- add key to any layer created with sepal-ui (#796)
- set max default zoom to 24
- directly use localtileserver
- add key to any layer created with sepal-ui

### Refactor

- **decorator**: remove legacy debug param from decorator
- **decorator**: raise a warn if debug param is set on loading_button and catch_error decorators
- **VersionCard**: use color.main on version card
- use the pytest fixture for tmp directory (#890)
- reset to empty strings instead of None
- fix doc error
- **readme**: revert to empty
- drop the tmp_dir
- use the pytest fixture for tmp directory
- remove gdal
- update module_venv bin to align with sepal
- **version_card**: use tomli instead of toml
- use tomli instead of toml (#888)
- use tomli instead of toml
- fix typing parameters
- use pyproject.toml to get module version
- update nox documentation session
- deprecation warning, index shoul always rely on iloc
- AdmNames
- use the class implementation
- cleaning
- use pygaul and pygadm to manage admin names
- test should go inside the with statement
- use the Optional typing
- only use typing_extentions for Self type
- improve compactness (#841)
- 0 bytes files are now behaving as the others
- improve compactness
- use double quote for the run command (#857)
- use double quote for the run command
- use nested method in get_assets
- typo
- make asset_list a private parameter
- delete legacy test file
- remove legacy test file
- typo
- typo
- set a default zoom for rasters and map

## v_2.16.4 (2023-05-25)

### Fix

- replace jslink by link (#829)
- trim the asset input (#830)
- use deprecated from tantale (#831)
- use tantale deprecated in RDT build
- use deprecated from tantale in github actions
- use deprecated from tantale in noxfiles
- trim the asset input
- replace jslink by link
- adapt to latest planet SDK
- update test subscriptions
- remove references to FAO (#821)
- remove FAO logo from disclaimer
- align the checkbox on the layer states (#819)
- align the checkbox on the layer states

### Refactor

- update disclaimer messages

## v_2.16.3 (2023-04-11)

### Fix

- remove pin on dialog and menu z-index (#787)
- only use tqdm parameters after reset (#814)
- freeze back layers_control width (#815)
- freeze back layers_control width
- only use tqdm parameters after reset
- remove pin on dialog and menu z-index

## v_2.16.2 (2023-04-06)

### Fix

- get_mosaics and get_quad in planetModel (#809)
- typo
- typo
- get_mosaics and get_quad in planetModel
- add a custom MarkerCluster (#807)
- save the credentials in planet_model (#808)
- save the credentials in planet_model
- remove size constraints on LayersControl
- add a MarkerCluster
- launch map__app in jupyter notebook
- launch panel_app in jupyter notebook

## v_2.16.1 (2023-03-28)

### Fix

- repair draweritems (#802)
- stop using partial methods in traits
- use agg backend in tests (#795)
- use agg backend in tests
- limit to plans ids
- typo
- avoid refactoring autogenerated files
- prevent vinspector close on click (#788)
- make search_key a classmethod
- drop tmp (#790)
- drop reclassify module (#785)
- tempdir in VectorFile Fixture
- prevent vinspector close on click
- drop reclassify module

### Refactor

- typo
- use list comprehension for small loops

## v_2.16.0 (2023-03-08)

### Feat

- add a fullscreen parameter to display bigger menu in map applications (#756)
- add a nox session to run application locally (#775)

### Fix

- use fork of deprecated
- use latest version of gadm (4.1)
- build the coverage analysis with nox as well (#773)
- add a today method to datepickers (#758)
- catch FileNotFoundError
- pin sphinx-favicon to latest version (#776)
- pin sphinx-favicon to latest version
- run local sessions in debug mode
- apply the modification to panel applications as well
- loose requirements on deploy
- move the entry-point in the pyproject.toml
- use a pyproject.toml for parameters
- create a noxfile to run apps
- add root parameters in FileInput (#774)
- don't use is_related_to method
- add root parameters in FileInput
- build the coverage analysis with nox as well
- update bg color when menu is activated
- close menu when clicking outside
- add a today method to datepickers Fix #752
- create a fullscreen menu control

### Refactor

- use patched versions of sphinx and deprecated (#784)
- add back versionadded
- move patched versions to builder to avoid blocking conda release
- update the tests (#780)
- lint tests as well
- drop legacy object structure
- respect D212
- improve FileInput typing
- drop use of spelling extention (#762)
- drop use of spelling extention
- cleaning

## v_2.15.2 (2023-02-22)

### Fix

- increase z-index to avoid issues with select over dialogs (#766)
- increase z-index to avoid issues with select over dialogs
- add a marker on the map for inspection (#757)
- add html to the tested widgets (#764)
- add html to the tested widgets
- remove last fa5 icon (#748)
- add a marker on the map for inspection
- close tqdm when total is reached (#751)
- load autoreload extension before using it (#750)
- close tqdm when total is reached
- load autoreload extension before using it
- remove last fa5 icon

## v_2.15.1 (2023-02-08)

### Fix

- update package discovery (#742)
- update datepicker (#741)
- make get_children always recursive (#747)
- open first item autoamtically
- make get_children always recursive
- avoid layout_kwargs sharing among datepicker
- remove gliph when btn have only msg (#740)
- use attributes instead of _metadata (#739)
- change aoi color to primary (#738)
- use treeview to display vinspector
- discover packages automatically related to #734 need to be tested in the next fix release
- update v_model in both direction in datepicker Fix #730
- remove gliph when btn have only msg Fix #732
- use attributes instead of _metadata Fix #735
- change aoi color to primary Fix #736

### Refactor

- 1 line per data folder
- rename ValueControl

## v_2.15.0 (2023-02-07)

### Feat

- add a style parameter to generate aoi geojson
- manage basemaps
- upgrade the radio behavior
- add a checkbox to the layer_control
- use a custom layer_control
- add a simpleslider component

### Fix

- add vector management also fix some test bugs linked to get_children
- drop deprecated scenes (#729)
- drop deprecated scenes
- add extra line this line is invisble but ensures that the focusing animation of the radio button is not cut
- update control display
- use group to split layer control from the others
- avoid double border in zoom btn
- set max theoric level to 24
- auto-merge main in release
- propagate the aoi style in tile and view
- remove testing file
- remove fontawesome 5 from the html output
- inject fontawesome 6
- improve display of layer_control
- replace built-in ZoomControl

### Refactor

- remove isort parameters (#728)
- install the appropriate pre-commit at once
- remove isort parameters
- use get_children instead of search_radio
- make get_children more flexible new arguments: klass, attr, value
- single call to display
- add styling with HTML instead of widgets
- always use the gejsjon to display aoi
- use doc8 on our docs
- move map-btn css from json to css file

## v_2.14.2 (2023-01-25)

### Fix

- read resize_trigger js as text. Closes #709
- read resize_trigger js as text. Closes #709

### Refactor

- write about_tile in 2 lines

## v_2.14.1 (2023-01-14)

### Refactor

- don't prettify CHANGELOG.md

### Fix

- add checks for bin content  (#701)

## v_2.14.0 (2023-01-11)

### Refactor

- apply all ruff rules
- first draft of ruff refactoring
- use setdefault
- use setdefault
- drop the gee reading to get the bounds
- typo
- drop the gee reading to get the bounds Fix #681
- update imports
- move js code away from copytoclip python file
- remove video extention
- remove video extention
- translator package
- remove typehint
- improve the quality of frontend files
- lint the frontend files

### Fix

- reduce the size of the lib
- stop downloading geodataframe and use json instead
- remove ee_token script
- type hinting for reclassify module was wrong
- error while building reclassify module
- use sd instead of su decorator
- remove alert parameter from AoiModel
- translate password label
- use fa6 icon in password
- add type_extentions to toml file
- setup license file
- use build command
- planet_api request
- use fa6 instead of mdi
- mypy errors
- create a stub file for the overwritten widgets
- solve typ hinting issues
- typo in type hint
- use github repository for flake8
- stop relying on my service account for auth
- drop instafail
- source should be a list
- autoreload the notebooks for prototype phase
- autoreload the notebooks for prototype phase
- add a modue.yaml file
- translator issues
- handle empty dict
- test both python and notebook files
- typo remove mypy
- add a modue.yaml file Fix #563
- do not rely on harversine
- set dialog on top of everything
- do not rely on harversine
- set dialog on top of everything but the drawers Fix #649
- base the linting on pre-commits
- base the linting on pre-commits

### Feat

- use type hint on every function/method/class

## v_2.13.0 (2022-12-11)

### Fix

- drop use of Request from planet
- drop use of Request from planet The method was removed from the lib between 2.0.a2 and 2.0.a6
- update_progress accept values >1
- remove left when only icon is set
- update_progress accept values >1
- replace all deprecated fas and far
- remove left when only icon is set
- change map application title Fix #642
- update all relaining gee widgets
- support pathlib path Fix #628 Fix #629
- create a specific aoi_dc on the map
- adapt to most recent gee token
- create a specific aoi_dc on the map Fix #595
- set icon and text as traits in btn
- set icon and text as traits in btn
- keep default asset when reloading
- fixswitcher path for local build
- keep default asset when reloading
- set z-index to select content. closes #602
- legacy print

### Feat

- use fontawesome V6
- use the credential from the context to GEE oAuth
- add a method to set-up GEE credentials
- improve date picker widget customization
- add layout kwargs
- improve date picker widget customization. closes #600

### Refactor

- always keep msg and v_icon children
- use the cred fixture
- isort
- isort
- isort
- run latest isort
- run latest isort
- fileInput was using icon and text
- rename parameters in the reclassify module
- remove legacy prints

## v_2.12.0 (2022-09-13)

### Fix

- set the drawer on top of the appbar
- remove alert from aoi_model and add model as optional in aoi_view
- remove alert from aoi_model and add model as optional in aoi_view This is a solution in order to close #589
- set the navbar on top of the appbar

### Feat

- creates a default layer style to add_ee_layers. closes #425.

## v_2.11.2 (2022-09-01)

### Fix

- https://peps.python.org/pep-0440/#direct-references

## v_2.11.1 (2022-09-01)

### Fix

- https://peps.python.org/pep-0440/#direct-references

## v_2.11.0 (2022-09-01)

### Feat

- creates an overflow scrollbar when there is more than one subscription card
- add Sepal Map method to create and set legend
- hide legend when there is not content
- integrate levels of nicfi contract inside planet_view and planet_model
- add legend key to message box
- add Sepal Map method to create and set legend

### Refactor

- simplify structure
- support 'others' subscriptions
- small changes
- make optional model and trait, the object change method can be autonomously called
- upgrade planetapi object to match with planet>=2
- move to planet V2
- use message key for legend title

### Fix

- set all the links inlines
- FAO dark logo
- the logo is was wrong
- fix the json file
- transform legend into a legendControl
- #579
- fix imports error
- find forbiden keys recursivesly
- find forbiden keys recursivesly

## v_2.10.3 (2022-08-10)

### Fix

- lazy import localtileserver
- avoid reloading root when fileinput is already none

### Refactor

- .. spelling:word-list::
- reset method
- remove legacy print

## v_2.10.2 (2022-07-28)

### Fix

- use appropiate error
- lazy import of localtileserver

## v_2.10.1 (2022-07-25)

### Fix

- fix: add support for matplotlib cmap following advices from https://github.com/banesullivan/localtileserver/issues/103
- typo
- change raster detection
- drop usage of xarray-leaflet
- use class name
- close the controls when another one is opened Fix #551
- show alert when progess updates Fix #556
- set the navbar at the same z-index as map Fix #548
- remove toggle_button from map app Fix #549

### Refactor

- the alert is now fully compatible with tqdm
- the alert is now fully compatible with tqdm

## v_2.10.0 (2022-07-21)

### Refactor

- cleaning
- move decorator to their own modules
- move decorator to their own module
- isort the lib files
- remove matplotlib import
- edit style file structure
- change statebar behavior
- use json to store styling informations
- move check_input to utils
- use css and js file
- move check_input to utils Fix #513
- use noqa Fix #511
- deprecate zip_dir fix #514
- clean leftover + use tqdm.notebook
- use the new DrawControl to manage edited features
- aoi module

### Fix

- add the panel aaplication template
- add the map_app template
- add templates to the distibution
- update modul_factory
- stipout the notebooks
- trick to make sepal_ui work with Python 3.10
- use MenuControl in AoiControl
- use menucontrol with value inspector
- missing endif
- use a pattern in glob
- offset for the top navbar
- automatically nest tiles in menucontrol
- make the positioning optional
- add ipynb files to translator test
- use txt in mapbtn
- solve conflict with AoiControl
- be more specific in str testing
- lat/lng were inverted in haversine
- typo
- use relative path in tests
- remove existing unused keys
- solve all the issue created by moving color from style to init
- GeoJSON don't have loading member
- merge current master
- use 1single argument
- make the fulsscreen responsive to init status
- point to the correct variables in the translator Fix #521
- use txt in mapbtn Fix #510
- nest the card instead of the tile Fix #512
- remove unwanted notebooks
- describe the bug in the comment
- avoid mutate dc.data jsons. Identify circle geometries by type
- use search-location instead of at
- AppBar is not looking for the good one
- froze the Box to make sure it's never modified
- use box for encapsulated dict
- change color of the progress bar in alerts
- avoid bug on repeated click
- the points and vector were not triggering the v_model change event
- hide asset
- prevent crash when gee is set to false
- avoid 3.10 to be transformed in 3.1
- update translation keys
- hide the statebar on map build
- add the map loading state

### Feat

- add templates
- make it possible to change the menu size constraints
- add a menucontrol component
- first implementation of key_use
- open in fullscreen
- introduce tqdm progress bar. related with #294
- query only locales forlders
- add methods to deal with editions in DrawControl
- introduce tqdm progress bar. related with #294
- create an AoiControl widget

## v_2.9.4 (2022-06-09)

### Fix

- drop jupyter-sphinx git version I think the rendering is going to fail but it's preventing me from building the wheel and to use Jupyterlite I need the wheel Sorry not sorry

## v_2.9.3 (2022-06-09)

### Fix

- build the wheel

## v_2.9.2 (2022-06-09)

### Fix

- build the wheel

## v_2.9.1 (2022-06-09)

### Fix

- allow the build off the wheel

## v_2.9.0 (2022-06-09)

### Feat

- extend color simplenamspace to interactively display colors in …
- extend color simplenamspace to interactively display colors in jypyter
- refresh tooltip if there are new kwargs
- return basemap box as default object from basemaps module
- make wheel scroll default param
- add a MapBtn
- create planet handler
- add keys and fix review
- reset input fields when changing method
- capture any other errors, direcrtyl from api
- introduce StateIcon. An interactive icon.
- make alert and button optional elements
- create stand alone Planet credentials view
- create planet handler

### Refactor

- adapt tests to get the current theme"
- enrich color object to display both theme colors
- deprecate specific set theme and create generic function
- initialize configuration file and make it available to all modules
- improve zoom_bounds quality
- improve zoom_ee_object quality
- instantiate config parser and import in init
- deprecate is_absolute
- deprecate is_absolute
- overwrite default sw default Tooltip object
- rename tooltip wrapper widget
- remove uncalled skips
- set viz parameter outside of kwargs
- use keys for vinspector messages
- rename value inspector module and add a closing icon
- some line breaks and removed a pair of condionals
- reorder the coordinates
- move the v_inspector away from SepalMap
- cleaning
- split the gee command override from the rest of SepalMap
- use sepalwidgets StateIcon component
- admit any type for value trait
- add kwargs to the StateIcon
- make command cli tools as python scripts to align autoprogram plugin
- make parser var name descriptive and add module commands to path
- use a fake init key
- undo test
- remove dust
- raise error when credentials empty
- move theDrawControl to its own file It will be supporting the drawing methods (editing, polygonize) from there
- clean the import of ipyleaflet widgets
- add translation keys for navdrawer items
- add translation keys for navdrawer items
- rename files
- rename planet to avoid main planet package ambibuity

### Fix

- zoom automatically on raster layers
- digest all ee.ComputedObject
- legacy assert
- fullscreen control now specify which map to fullscreen
- add the none_ok parameter to find_layer
- remove bind method from Alert
- skip planet test if no API key
- remove bind method from Alert Fix #295
- skip planet test if no API key Fix #481
- add_tooltip method
- typo
- include a base filter to sepal_map search and delete methods
- prepare refactoring of ValueInspector
- avoid the v_inspector to move down the map
- remove legacy dot on the map Fix #456
- inspect rasters
- read GeoJSON data
- inspect ee_objects
- remove background for btns on maps
- closes #466
- doc typo
- typo
- closes #466
- validate when there is no initial value in module
- add missing import
- use quotes to define the planet_credentials
- remove empty string from the translation dict
- use keys for the fileinput placeholder Fix #464
- avoid circular reference
- geemap was still called in aoi_model
- remove_all method to remove all layers but the basemaps
- overwrite remove_layer to use index, name or layer
- find layer by name and by index
- set the basemaps as basemaps #422
- drop usage of geemap + cleaning #455
- continue using geemap 0.8.9
- remove empty string from the translation dict Fix #449
- fix #452

## v_2.8.0 (2022-04-18)

### Fix

- remove empty versions from the changelog
- prevent Alert with no parameters to raise a warning
- backward compatibility of the type parameter
- use msg for banner btn
- only display the oldest banner queue the other and hide them
- raise a warning if type is badly defined
- display the number of stackbar in the queue
- create the disclaimer tile on the fly
- change logo source in light theme
- unproject images in add_raster
- unproject images in add_raster Fix #434

### Feat

- new set and get children to sepalwidget. Aims to close #443
- create Banner widget to display important message to end-user
- override ipyleaflet Map add_layer method to use default style

### Refactor

- rename \_tmp class name with the actual new sepalwidget name
- deal with type\_ the same way we do it in Alert
- use a persistent parameter instead of timeout
- simplify add_banner method by calling Banner widget
- return map when new layer added + make more clear param name
- change alert by snackbar when creating a banner aims to close #438
- move theme, color and theme function to styles

## v_2.7.0 (2022-03-28)

### Refactor

- get folder name instead stem
- change kernel by venv. reset df index
- clean leftover
- don't use shell=True
- reduce line number
- sanityse scripts
- cleaning
- use observe decorator
- observe alert trait even though no model

### Feat

- cmd script to activate virtual envs
- warn user this process will take some time
- avoid adding multiple banners
- control the theme using a btn
- add theme in the config file
- add interaction with drawer. closes #415
- new fullscreen widget
- new LocaleSelect widget
- function to update config language
- allow the tranlator to read config file
- new fullscreen widget

### Fix

- use repository name instead of stem
- guess the languages available
- check that the folder is a module directory
- add a script to test enviroment
- remove alert if change of the same parameter
- set return statement
- trigger the icon change
- display only one alert per type use a lambda function and next intead of multiple ifs. set the v_model to false to systematically see the transition
- specify the archive format
- solve build issue in RDT
- typo in attribution map
- the lib translator was still using the old implementation
- display message to the end user when changing theme
- change menus colors according to theme
- control selected aoi color
- adapt map basemap to theme
- control the theming with the config file
- control datepicker value using v_model
- us all .json in l10n folders
- create a script to switch language parameters from terminal
- display only the locales available for the current app
- display only the locales available for the current app
- use mdi icons in Numberfields
- password eyes not diplayed
- use mdi icons for pre-designed prepend-icon Fix #414
- display messages to the end user on locale change
- make the localSelector responsive to translator values
- add the Local widget in the navbar
- change config file on click
- debug non working flags
- support for subvarieties of language Fix #408
- add a disabled trait to datepicker Fix #409

## v_2.6.2 (2022-02-18)

### Fix

- prevent crash when badly design viz params are used Fix #405

## v_2.6.1 (2022-02-17)

### Fix

- add the message file in the distrib
- make readme copatible with pypi release
- make readme compatible with pypi release has syntax errors in markup and would not be rendered on PyPI. line 6: Error: Document or section may not begin with a transition.

## v_2.6.0 (2022-02-16)

### Refactor

- ignore untitled files
- ignore untitled files
- remove **setattr** magic method.
- typo in class name
- remove **setattr** magic method.
- reshape messages to fit the translator requirements
- replace every occurence of mdi icons
- use `/` in Path

### Fix

- remove fr file from merge
- avoid deprecation by reshaping dictionnary
- remove {locale}.json files
- remove list from json files potoon is not compatible with lists but only key dictionaries
- add basepath
- set the name in the properties of the GEJSON output
- don't use the named 'tmp' directory
- don't use the named 'tmp' directory Fix #391
- set the name in the properties of the GEJSON output Fix #390
- typo

### Feat

- change translator behaviour to meet l10n requirements

## v_2.5.5 (2022-01-12)

### Fix

- avoid meta sepal when clicking on download btn

## v_2.5.4 (2022-01-11)

### Fix

- scroll back to the top when change folde Fix #232
- only install pre-commit hooks once
- only install pre-commit hooks once Fix #373
- use https instead of git
- reset model output when selecting a new AOI Fix #366

### Refactor

- cleaning

## v_2.5.3 (2021-12-08)

### Fix

- solve the build issue in SEPAL
- cryptography since flake8 linting cryptography is not a lazy dependency anymore
- install missing packages

## v_2.5.2 (2021-12-07)

### Fix

- prevent bug when image have no properties Fix #361

## v_2.5.1 (2021-12-07)

### Fix

- git based libs are not compatible with pipy

## v_2.5.0 (2021-12-06)

### Refactor

- use named arguments to improve readability
- import sepal_ui after sys
- use flake8 in pre-commit
- reset github folder as hidden
- remove deprecation notice
- minor logical operator writing
- deprecate toggle
- use class management methods Fix #119
- use kwargs pop
- fix some of the parameters
- remove **init** in model
- use kwargs pop Avoid the duplication of parameter using an elegant and python method called dict poping
- add black basge Fix #326
- black typo
- remove legacy print
- typo in package name
- change lib name Change the lib name to meet the name used in PiPy Some change will need to be done in the documentation to reflect this change
- use \* instead of list comprehension

### Fix

- manage inverted bands
- display hsv images
- display categorical values without sld
- specific case of hsv display
- specific case of categorical data
- handle when the viz_name is not in the image
- overwrite addLayer to read metadata display parameters
- add the colors to the documentation Fix #312
- display folder as folder even when there is a suffix Fix #350
- display vrt file as images Fix #351
- change internal structure of widgets Improve coverage by testing markdown
- Sepalwidget set viz
- close fileinput menu when v_model is set
- close menu when date is selected Fix #17
- viz can be set in params
- make viz into a trait It now controls the vizibility
- hide the icon if set to empty
- set back the missing members
- hide the icon is set to empty
- add increm parameter
- change param
- reload assetSelect on types change Fix #323
- prevent setting asset of wrong type Fix #322
- limit the items list to type The self.items += is not a usable operator for list trait I was force to use a tmp list to really update the filter the items
- typo in Réunion name
- open link in new tabs Fix #311
- adapt test to new libs
- add a banner on top of app Fix #314
- init the items of the ClassTable Fix #313

### Feat

- overwrite all vuetify components
- overwrite all vuetify components

## v_2.4.0 (2021-10-19)

### Feat

- filter by column and value in AOI.
- filter by column and value in AOI. - closes: #296

### Fix

- display specific warnings in alerts
- replace default v_model fon VectorField as trait
- doc build failed
- only display SepalWarning in Alerts
- this assignation was overwritting the w_asset dict
- vector field method. closes #306

### Refactor

- make v_model default and empty value as None instead of empty string
- be consistent when concatenating

## v_2.3.0 (2021-10-06)

### Fix

- add enforce_aoi to reclassify_model
- use split instead of indexing Fix #302
- prevent tooltip error when calling. closes #298
- prevent tooltip error when calling. closes #298
- little typo
- fiix some minor bugs and add human sorted

### Refactor

- create destination gee unique name before export
- move exceptions from view to model
- remove \_chk_dst_file method, its process was duplicated in the \_set_dst_class file method

### Feat

- new script to Create a string followed by a consecutive underscore and number
- test reclassify model coverage=80%
- create useful fixtures to implement in related tests.
- create a tests rasters to test reclassify methods

## v_2.2.1 (2021-09-30)

### Fix

- typo in version naming

## v_2.2.0 (2021-09-30)

### Fix

- use ssh url in module_factory Fix #283
- typo
- clip margins
- use RPC to serve the resize method
- use RPC to serve the resize method
- catch when on_widget and targets have different length
- get the widget instead of the widget name
- local variable referenced before assignment
- **docs**: fix typo
- include the save parameter to the view when someones initialize the view without the model

### Refactor

- remove un-used method
- renamed Clip -> CopyToClip
- only set targets at the begining
- create a state bar to control if a table is already created
- use switch decorator
- make all view children elements part of the View class

### Feat

- declare all variable
- Copy to clipboard
- add copy-to-clipboard widget
- create common used fixtures
- add a targets parameter to switch method
- test reclassify model
- add a target parameter in the switch method
- create validation for the reclassify model method

## v_2.1.1 (2021-09-15)

### Fix

- typo in setup

## v_2.1.0 (2021-09-15)

### Fix

- folder init in reclassifyTile
- typo in json dict
- display the btn at the bottom of the table
- display a message to the user when reclassify
- default to 0 if class is not specified
- use the SEPAL coloring parameters
- use the folder name
- small UI bug
- use init_ee instead of ee.initialize()
- import table
- minor typo
- remove type and feat: introducing switch decorator
- remove type

### Refactor

- **lang**: add keys
- remove test notebook
- ensure a value is set to the func
- only set w_image to the appropriate widget
- add new keys in translation
- remove ununsed break
- fix merge conflict
- only init ee if needed
- remove usage of gee in documentation
- remove unused file
- change the image visualization function (black-formatter).
- extend the behavior of switch decorator with the last comments. closes #263
- adapt table view widget to the parameter SCHEME. Remove ambiguity when handling widgets values by adding \_metadata attribute
- move SCHEMA variable from translation key to parameters to avoid ambiguity
- drop pre-commit autoupdate
- typo
- reintroduce type attribute
- fix french typos
- create **all** variable to fix imports
- place **all** at the file start

### Feat

- change state when something is loaded
- test asset validity
- add commitizen check
- improve sanity checks
- separate the reclassified image and its visualization
- define default_asset trait in SelectAsset. it will accept whether strings for unique default assets or lists for multiple. The trait can be observed to update the list anytime
- introducing switch decorator
- improve assetSelect component
