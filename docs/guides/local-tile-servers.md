# Local Tile Servers Behind SEPAL

> Use this guide when an app serves tiles from a server running inside the
> kernel — `localtileserver` for rasters, `vectortileserver` for PMTiles — and
> those tiles have to reach the browser.

## The Problem

Both tile servers run _in the kernel process_ and bind `127.0.0.1:<port>`. Unless
the browser happens to be on that same machine, `http://127.0.0.1:41029/...`
means nothing to it, so tiles silently fail to load — no error, just an empty
map.

Something has to carry those bytes across. **Which mechanism is correct depends
on how the app is deployed**, and picking the wrong one is either broken or
unsafe.

### pysepal 5 draws with MapLibre, which fetches its tiles

ipyleaflet loaded a tile with an `<img>` element, which any origin may serve.
MapLibre fetches it, and a fetch to another origin than the page's needs CORS
headers. `localtileserver` sends none by default (`TileClient(cors_all=False)`),
and pysepal does not turn them on. So even a browser on the kernel's machine
can no longer load the loopback URL directly; the tiles reach it only through
one of these:

- **A same-origin route** — the prefix SEPAL sets, `jupyter-server-proxy` in
  JupyterLab, the route pysepal mounts under solara-server, or one you mount
  (configurations 2 and 3). The fetch never leaves the page's origin.
- **The comm bridge** — outside solara-server, pysepal turns jupyter-loopback's
  bridge on for every local raster. It catches the fetches to the tile port and
  tunnels them over the kernel websocket, so a plain `voila notebook.ipynb` with
  the empty prefix below still shows its rasters.

Without either, the browser blocks every tile while the tile server logs `200`
for each: the map stays empty and the console logs `AJAXError: Failed to fetch (0)` per tile.

The bridge cannot serve solara-server. Its widget is one per process and shows
only where `IPython.display` puts it, which under Solara is no page at all, so
`window.__jupyter_loopback__` never exists there. That is why pysepal mounts its
own route there instead (configuration 2).

## What Decides the Answer

Two questions, in order.

**Which server puts the page in front of the browser?** Not which framework the
app is written in — a pysepal app built from `solara.component` can be served by
`solara run` _or_ by Voila, and the answer differs.

| Configuration                           | Process model                                           | Carries the bytes                         |
| --------------------------------------- | ------------------------------------------------------- | ----------------------------------------- |
| Served by Voila/Jupyter, user sandbox   | One container per user; kernel is its own process       | A prefix the host serves (SEPAL sets one) |
| Served by solara-server, own container  | One container, one Solara process, one user             | pysepal's route, or one you mount         |
| Served by solara-server, `app-launcher` | One shared container, many authenticated users, proxied | Same, **with per-session authorization**  |

**What is the browser actually asking for?** This decides whether the tile server
can leave the request path at all:

| Package            | The browser requests                       | Already on disk?            |
| ------------------ | ------------------------------------------ | --------------------------- |
| `vectortileserver` | a byte range of `basins.pmtiles`           | **Yes** — it is the archive |
| `localtileserver`  | `api/tiles/{z}/{x}/{y}.png` + style params | **No** — rendered on demand |

`localtileserver` builds an XYZ template and rio-tiler renders each PNG from the
GeoTIFF per request, applying colormap, band selection and stretch. Nothing on
disk matches the request, so the tile server has to stay in the path. PMTiles is
the opposite: the archive already is the payload.

The test, whichever package you are on: **does the response already exist on
disk?**

## Configuration 1: Served by Voila or Jupyter

### The rule: only use a prefix something actually serves

"Voila" is not one deployment. A prefix is a promise that some proxy serves that
path, and whether the promise holds is what decides everything here.

**Voila inside SEPAL keeps it.** SEPAL launches the app and sets
`LOCALTILESERVER_CLIENT_PREFIX` to a route on its own origin. An explicitly set
variable wins outright — localtileserver reads it and never autodetects — so
tiles take the fast same-origin HTTP path and nothing below applies. Leave it
alone.

**A plain `voila notebook.ipynb` does not.** Voila is a Jupyter _kernel_ but not
a _jupyter-server_, so no `jupyter-server-proxy` route exists. With the variable
unset, localtileserver autodetects one anyway — being in a kernel is all it
checks — and every tile 404s:

```
404 GET /voila/files/localtileserver-proxy/39541/api/tiles/8/143/129.png
```

Voila redirects the unknown path to its `/voila/files/` allowlist, which 404s.

The comm bridge cannot rescue that invented prefix, because jupyter-loopback
0.3.3's prefix handling is broken in exactly this situation
([issue #3](https://github.com/banesullivan/jupyter-loopback/issues/3),
[PR #2](https://github.com/banesullivan/jupyter-loopback/pull/2), both open):

- `probePrefix()` treats any non-404 as "the HTTP proxy is live". Voila answers
  the probe with **405**, so the shim keeps the dead HTTP path.
- `interceptMatch()` returns early for same-origin localhost URLs whose port is
  not a registered tile port — which is what a prefix URL looks like when the
  page itself is served from `127.0.0.1`.

Both are prefix-only, and both need the local case: bug 1 only hurts when nothing
really serves the path, and bug 2 needs a `127.0.0.1` page origin, which
`sepal.io` is not. So they bite the deployment where you want no prefix anyway.

**With no prefix registered**, the tile URL is the plain loopback URL and
`widget.js` takes its localhost branch: the port _is_ in `interceptedPorts`, so
it returns `status: "broken"`, which the file documents as "route through the
comm bridge". No probe runs, so neither bug is reachable — 0.3.3 works as
shipped, and you do not need PR #2 merged.

### `vectortileserver`: nothing to do — only if the browser is local

It never autodetects, because autodetection cannot be trusted (its own
`configure.py` cites the Voila 405), so its default URL is the plain loopback
one. When the browser sits on the same machine as the kernel that is enough:
build a layer and it works.

**When the browser is elsewhere it is not enough.** On a SEPAL sandbox
`http://127.0.0.1:8000/...` names the viewer's own laptop, so PMTiles silently
never arrive — an empty map with no error, while rasters on the same page render
fine because SEPAL set _their_ prefix.

Give it the same route. SEPAL's is jupyter-server-proxy's generic
`/proxy/{port}`, which forwards any port in the sandbox, so it carries PMTiles
just as well as tiles:

```bash
export VECTORTILESERVER_CLIENT_PREFIX="$LOCALTILESERVER_CLIENT_PREFIX"
# on SEPAL both are /api/sandbox/jupyter/proxy/{port}
```

Measured through that route: `206` with `Content-Range: bytes 0-99/52315` and
`Accept-Ranges: bytes`, so the range requests PMTiles depends on survive it.

Only borrow the raster variable when it is the generic `/proxy/{port}` form.
`localtileserver`'s own autodetected value is namespaced to itself
(`localtileserver-proxy/{port}`) and would not serve a vector tile port.

Do the borrow in the app rather than the launcher when you do not control the
launch environment, which under SEPAL you usually do not:

```python
# app.py, before anything imports vectortileserver
_raster_prefix = os.environ.get("LOCALTILESERVER_CLIENT_PREFIX")
if _raster_prefix and "/proxy/{port}" in _raster_prefix:
    os.environ.setdefault("VECTORTILESERVER_CLIENT_PREFIX", _raster_prefix)
```

`setdefault` leaves an explicitly configured value alone. Test _for_
`/proxy/{port}` rather than _against_ `localtileserver-proxy`: a denylist also
borrows a raster-specific route such as Configuration 2's `/rasters/{port}`, and
the PMTiles then 404 silently — the failure this guard exists to prevent. The
empty value the next section asks for is falsy, so the plain-Voila case borrows
nothing and both libraries keep the loopback URL, which is what works there.

### `localtileserver`: define the prefix empty — when nothing serves one

This one **does** autodetect, and that is what breaks the unhosted case: inside
any Jupyter kernel it manufactures `localtileserver-proxy/{port}` whether or not
anything serves it. Under SEPAL the variable is already set, so this never fires;
it is the plain `voila notebook.ipynb` case that needs the override.

```bash
LOCALTILESERVER_CLIENT_PREFIX=      # defined, and empty — not unset
```

Empty is the one value that suppresses both the environment read and the
autodetect, because localtileserver only reads the variable when it is non-empty
and only autodetects when no prefix and no host are set. `add_raster` passes the
variable straight through to `TileClient`, so the browser gets
`http://127.0.0.1:<port>` and the bridge intercepts it. Under MapLibre the
bridge is the only thing carrying those tiles: the loopback URL is another origin
than the page, so they load in this configuration only while the bridge is on.

**`LOCALTILESERVER_DISABLE_JUPYTER_LOOPBACK` does not help here**, and makes
things worse: it only guards the comm bridge, so it removes the fallback while
leaving the unreachable prefix URL in place. Reach for it only in Configuration 2
or 3, where a real route serves the tiles.

### The comm bridge is a fallback, not a plan

With no prefix set, both libraries stand up jupyter-loopback's comm bridge
themselves — `vectortileserver`'s `create_leaflet_layer` calls its
`enable_for_port` helper, and pysepal calls `TileClient.enable_jupyter_loopback()`
for every local raster. It tunnels loopback fetches over the kernel's websocket;
pysepal does not configure it beyond that call.

Do not plan around it. Under ipyleaflet, where it was seen to work, the browser
was on the same machine as the kernel and could reach the loopback URL anyway,
so the bridge was never the thing carrying the bytes. Under MapLibre it is: with
the bridge off, the same local setup shows no raster (see the section on MapLibre
above). It has still not carried tiles to a genuinely remote browser — the one
time that was tried, PMTiles on a SEPAL sandbox with no prefix, nothing arrived.

Use a prefix wherever the host gives you one, which on SEPAL is always. Turn the
bridge off explicitly (`LOCALTILESERVER_DISABLE_JUPYTER_LOOPBACK=1`,
`VECTORTILESERVER_DISABLE_JUPYTER_LOOPBACK=1`) once a route is serving the tiles,
so a working deployment does not also carry an unused loopback-fetch primitive.

### Worked examples

`demo_apps/solara_raster_app/` and `demo_apps/solara_vector_app/` both run under
Voila via their `ui.ipynb`. The vector demo needs the `demos` extra plus
`tippecanoe` (conda-forge; pip cannot provide it).

## Configuration 2: Served by solara-server, Own Container

The page origin _is_ the Solara server, so tiles travel over ordinary
same-origin HTTP. **For rasters, pysepal does this for you**: with
`LOCALTILESERVER_CLIENT_PREFIX` unset, the first local raster puts a route at
`{root_path}/_pysepal/tiles/{token}/{port}/...` in front of Solara's own routes
and points the tile URLs at it. A stock `solara run` needs nothing else. Under
solara-server pysepal never turns the bridge on, prefix or not.

The route forwards only tile paths (`api/tiles/{z}/{x}/{y}.png`), and only for
the tile server and file a token was granted for: `localtileserver` opens
whatever path or URL a request names in `filename`, so anything less would hand
the page a file reader. Each raster gets its own random token, which only the
page that drew it receives, and the grant ends when the layer's tile client is
released. A page that knows another user's file path still cannot read it, so
the route is also safe where users share one process (configuration 3).

A set prefix wins: SEPAL's, or your own route's below, and pysepal's route is
not used.

Which route you mount yourself follows from the payload question above: PMTiles
can be served as a file, rasters must be proxied to the tile server.

### Mount the route

Solara's `starlette.py` ends with catch-all routes that swallow any route added
after them; pysepal's goes in front of them at run time. Solara documents the
alternative
under
[Deploying / self-hosted → Embedding in an existing Starlette application](https://solara.dev/documentation/getting_started/deploying/self-hosted):
point `SOLARA_APP` at your app file and compose the routes yourself.

```python
from starlette.applications import Starlette
from starlette.routing import Mount, Route
import solara.server.starlette as solara_starlette

async def archive(request):   # PMTiles: open the file, stream the range
    ...

async def raster(request):    # rasters: forward to the tile server
    ...

app = Starlette(
    routes=[
        Route("/tiles/{kernel_id}/pmtiles", endpoint=archive),
        Route("/rasters/{port:int}/{path:path}", endpoint=raster),
        Mount("/", routes=solara_starlette.routes),  # must be last
    ],
    lifespan=solara_starlette.lifespan,
    middleware=solara_starlette.middleware,
)
```

```bash
SOLARA_APP=app.py uvicorn asgi:app --host=0.0.0.0 --port=8768 \
    --root-path=/api/app-launcher/<module>
```

Solara's own snippet mounts under a `/solara/` prefix and passes neither
`lifespan` nor `middleware`. Pages still render without them — but you lose gzip,
the session and authentication middleware when auth is enabled, the startup
validation in `on_startup` (`ensure_apps_initialized`, `validate_state_settings`),
and the state-worker drain in `on_shutdown`. Pass both, as above.

Passing `middleware` also puts `GZipMiddleware` in front of _your_ routes, and
Starlette's gzip never looks at the status code. A `206` big enough to compress
comes back with `Content-Length` describing the compressed body beside a
`Content-Range` describing the uncompressed slice, and every range PMTiles asks
for is re-packed. Declaring an encoding makes the middleware pass the response
through (measured on Starlette 0.52 and 1.3):

```python
return FileResponse(path, headers={"content-encoding": "identity"})
```

Mount Solara at `/` rather than a prefix when it owns the app root, and list your
own routes before it so the catch-all does not swallow them.

A proxying raster route must forward the `Range` request header and preserve
`206 Partial Content`, and drop hop-by-hop headers (`connection`,
`transfer-encoding`, `content-length`) when relaying the response.

### Point the tile servers at it

```bash
export LOCALTILESERVER_CLIENT_PREFIX=/rasters/{port}
export LOCALTILESERVER_DISABLE_JUPYTER_LOOPBACK=1

export VECTORTILESERVER_DISABLE_JUPYTER_LOOPBACK=1
```

Both packages substitute `{port}` when the prefix is read. The
`*_DISABLE_JUPYTER_LOOPBACK` variables stop the libraries from also standing up
the comm bridge behind your back — without them you get both paths, and the
bridge widget (and its loopback fetch primitive) is mounted even though nothing
needs it.

`VECTORTILESERVER_CLIENT_PREFIX` is deliberately absent above: the archive route
keys on the kernel, so set it per client rather than process-wide.

```python
TileWorkspace(
    client_prefix=f"{root_path}/tiles/{kernel_id}",
    allowed_directories=[session_tile_dir(kernel_id)],
)
```

Read `root_path` from `solara.server.settings.main.root_path` (`None` when unset)
so the URL carries the app-launcher prefix — a bare `/tiles/…` 404s behind the
proxy.

No modification to either library is required. This is the mechanism
`jupyter-server-proxy` uses in JupyterLab; you are simply aiming it at Solara.

## Configuration 3: `app-launcher`

One container runs Solara; authenticated SEPAL users are proxied in by the
app-launcher module. **Many users share one process and one container.**

`jupyter_loopback`'s built-in fetch handler takes the port, path, method, headers
and body straight from the frontend message and performs the request kernel-side.
There is no allowlist — `intercepted_ports` only tells the _browser_ which URLs
to rewrite; it is never checked in Python. A naive proxy route has exactly the
same property.

So either mechanism gives every user's page an arbitrary `127.0.0.1` fetch
primitive inside a container shared with other users. Concretely: user A adds a
raster, `localtileserver` binds `127.0.0.1:PA` with no authentication; user B's
page asks for port `PA` — a small range, trivially scanned — and reads A's tile
data.

Turn the comm bridge off here (`*_DISABLE_JUPYTER_LOOPBACK=1`) rather than
leaving it as a fallback. pysepal's own raster route (configuration 2) is safe
here: it forwards only what a per-raster token grants. If you mount your own,
take the upstream port and file from server-side state — what this app started,
keyed by session — rather than from the URL, or you have rebuilt the same
primitive over HTTP.

### Serve the archive, not the tile server

For PMTiles, drop the loopback HTTP server from the browser path entirely.
`vectortileserver`'s browser-facing surface is a single endpoint
(`endpoints.py:pmtiles_endpoint`) that streams bytes out of a PMTiles file with
range support. Style and metadata are computed kernel-side from the archive, so
**the browser only ever needs the archive bytes.**

That matters more than convenience here: `TileServer` is a process-wide singleton
and each client's `allowed_directories` are merged into that one shared config,
so its endpoint is only ever as restrictive as the most permissive client. Serve
the file yourself and it is never exposed.

`starlette.responses.FileResponse` already emits `accept-ranges: bytes`, parses
`Range`, and returns `206` / `416` correctly, which is exactly what PMTiles
needs.

### Authorize per session

Write each session's archives under a directory keyed by kernel id, then have the
route verify the requester owns that kernel. Solara does precisely this for its
own eviction route (`solara/server/starlette.py`), which is the pattern to copy:

```python
context = kernel_context.contexts.get(kernel_id, None)
if context is None:
    return Response(status_code=404)
session_id = request.cookies.get(server.COOKIE_KEY_SESSION_ID)
if not session_id or session_id != context.session_id:
    return Response(status_code=403)
```

`COOKIE_KEY_SESSION_ID` is `"solara-session-id"`, set by solara on the page
response, so the browser sends it with every tile request on the same origin.
`VirtualKernelContext.session_id` records the session that owns the kernel. Fail
closed: 404 for an unknown kernel, 403 for a mismatch.

Resolve the file inside the session directory and confirm the resolved path is
still under it before serving — an id or filename arriving from the URL must
never be able to escape via `..`.

## Environment Variable Reference

| Purpose                    | `localtileserver`                          | `vectortileserver`                          |
| -------------------------- | ------------------------------------------ | ------------------------------------------- |
| Browser-facing URL prefix  | `LOCALTILESERVER_CLIENT_PREFIX`            | `VECTORTILESERVER_CLIENT_PREFIX`            |
| Disable the comm bridge    | `LOCALTILESERVER_DISABLE_JUPYTER_LOOPBACK` | `VECTORTILESERVER_DISABLE_JUPYTER_LOOPBACK` |
| Constructor argument       | `TileClient(client_prefix=...)`            | `TileClient(client_prefix=...)`             |
| Autodetects a proxy prefix | Yes — the Voila trap                       | No — must be set explicitly                 |

An **empty** `*_CLIENT_PREFIX` forces the loopback URL; **unset** is not the same
thing, and for `localtileserver` means "autodetect".

## Security

The comm bridge and a naive proxy route are the same primitive over different
transports: arbitrary HTTP (and WebSocket, for the bridge) to any loopback port,
initiated by whatever runs JavaScript in the app page.

- **Single-tenant container** (configurations 1 and 2): within the existing trust
  boundary — the page can already reach everything the user can. It still becomes
  a real vector if the app ever renders untrusted content into the page.
- **Shared container** (configuration 3): it crosses a tenant boundary. Restrict
  ports to those the app started, and authorize per session.

Adding a port allowlist to the proxy route costs a few lines and is what keeps an
app portable from configuration 2 to configuration 3.

## What Has Been Verified

| Claim                                                                  | How                                                                                                                                                             |
| ---------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| An autodetected prefix 404s under standalone Voila                     | Ran it — the 404 above is from that log                                                                                                                         |
| An empty `LOCALTILESERVER_CLIENT_PREFIX` fixes it                      | Ran it under ipyleaflet and again under MapLibre — raster renders, zero proxy 404s                                                                              |
| Under MapLibre the bridge carries the loopback tiles under Voila       | Ran it: plain Voila with the empty prefix shows a local raster, with no request to the tile port on the network                                                 |
| ...but never under solara-server                                       | Ran it: stock `solara run`, first page and after a reload: no `window.__jupyter_loopback__`, `Failed to fetch (0)` per tile, `200` in the server log            |
| pysepal's route carries them under solara-server                       | Ran it: stock `solara run`, first page and after a reload: the raster draws from `/_pysepal/tiles/{port}`; `tests/test_layers/test_tile_route.py` pins the 404s |
| `vectortileserver` needs no configuration when the browser is local    | Ran it under ipyleaflet — PMTiles render with nothing set; not rerun under MapLibre                                                                             |
| ...but not when it is remote                                           | Reported from a SEPAL sandbox: empty map, rasters fine                                                                                                          |
| SEPAL's `/proxy/{port}` route carries a vector tile port too           | Ran it on the sandbox — 200, and 206 with `Content-Range` for a range request                                                                                   |
| A set variable wins outright, so autodetect never runs                 | Ran `get_default_client_params` across unset / set / empty                                                                                                      |
| SEPAL-hosted Voila works on the prefix SEPAL sets                      | **Not run.** Follows from that precedence                                                                                                                       |
| The prefix-less loopback path avoids both jupyter-loopback bugs        | Read `widget.js`; the localhost branch returns `"broken"`                                                                                                       |
| Configuration 2 / 3 routes, and the bridge carrying a _remote_ browser | **Not run.** Read from source only — verify before relying on it                                                                                                |

Every run had the browser on the same machine as the kernel. Under ipyleaflet the
tiles could reach `127.0.0.1` directly; under MapLibre the bridge carried them under
Voila, and pysepal's route under solara-server.
That it also carries them when the browser is elsewhere — the SEPAL sandbox case
— follows from the `widget.js` branch above but has not been exercised end to end.
