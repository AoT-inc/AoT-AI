/**
 * leaflet-compat.js
 * Leaflet API Compatibility Layer for MapLibre GL
 * 
 * Provides Leaflet-compatible L.* APIs backed by MapLibre GL.
 * Enables existing Leaflet-dependent code to run without Leaflet.
 * 
 * Features:
 * - L.FeatureGroup (MapLibre Source + Layer)
 * - L.geoJSON (MapLibre GeoJSON Source + Layer)
 * - L.Circle / L.CircleMarker (GeoJSON polygon approximation)
 * - L.marker / L.divIcon (MapLibre Marker)
 * - L.Polyline / L.Polygon (MapLibre LineString/Polygon layers)
 * - L.MapLibreGL (for vector tile base layers)
 * - L.DomUtil (cursor classes)
 * - L.Draw.Event compatibility
 * - Coordinate utilities (L.GeoJSON.coordsToLatLngs)
 * 
 * @version 1.0.0
 * @requires maplibre-gl
 */

(function(global) {
    'use strict';

    if (typeof global.L !== 'undefined') {
        console.log('[LeafletCompat] Leaflet already present, skipping shim');
        return;
    }

    // =====================================================
    // L.DomUtil (Minimal - cursor support)
    // =====================================================
    const DomUtil = {
        addClass: function(el, name) {
            if (!el || !name) return;
            el.classList.add(name);
        },
        removeClass: function(el, name) {
            if (!el || !name) return;
            el.classList.remove(name);
        },
        create: function(tagName, className, container) {
            const el = document.createElement(tagName || 'div');
            if (className) el.className = className;
            if (container) container.appendChild(el);
            return el;
        },
        get: function(id) {
            return typeof id === 'string' ? document.getElementById(id) : id;
        },
        remove: function(el) {
            if (el && el.parentNode) {
                el.parentNode.removeChild(el);
            }
        },
        setTransform: function() {},
        setPosition: function() {}
    };

    // =====================================================
    // L.DomEvent
    // =====================================================
    const DomEvent = {
        on: function(el, type, fn, context) {
            if (!el || !type || !fn) return;
            el.addEventListener(type, fn.bind(context || this));
        },
        off: function(el, type, fn) {
            if (!el || !type || !fn) return;
            el.removeEventListener(type, fn);
        },
        stopPropagation: function(e) {
            if (e && e.stopPropagation) e.stopPropagation();
        },
        preventDefault: function(e) {
            if (e && e.preventDefault) e.preventDefault();
        },
        disableScrollPropagation: function() {},
        disableClickPropagation: function() {}
    };

    // =====================================================
    // L.LatLng
    // =====================================================
    class LatLng {
        constructor(lat, lng, alt) {
            this.lat = parseFloat(lat);
            this.lng = parseFloat(lng);
            this.alt = alt || 0;
        }
        equals(other) {
            return Math.abs(this.lat - other.lat) < 1e-9 && Math.abs(this.lng - other.lng) < 1e-9;
        }
        toString() { return `LatLng(${this.lat}, ${this.lng})`; }
        distanceTo(other) {
            const R = 6371000;
            const dLat = (other.lat - this.lat) * Math.PI / 180;
            const dLng = (other.lng - this.lng) * Math.PI / 180;
            const a = Math.sin(dLat/2)*Math.sin(dLat/2) +
                      Math.cos(this.lat*Math.PI/180)*Math.cos(other.lat*Math.PI/180)*
                      Math.sin(dLng/2)*Math.sin(dLng/2);
            return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
        }
    }

    // =====================================================
    // L.LatLngBounds
    // =====================================================
    class LatLngBounds {
        constructor(corner1, corner2) {
            if (corner1 && corner2) {
                this._southWest = new LatLng(
                    Math.min(corner1.lat, corner2.lat),
                    Math.min(corner1.lng, corner2.lng)
                );
                this._northEast = new LatLng(
                    Math.max(corner1.lat, corner2.lat),
                    Math.max(corner1.lng, corner2.lng)
                );
            } else {
                this._southWest = new LatLng(90, 180);
                this._northEast = new LatLng(-90, -180);
            }
        }
        getSouthWest() { return this._southWest; }
        getNorthEast() { return this._northEast; }
        getCenter() {
            return new LatLng(
                (this._southWest.lat + this._northEast.lat) / 2,
                (this._southWest.lng + this._northEast.lng) / 2
            );
        }
        isValid() { return this._southWest && this._northEast; }
        contains(latlng) {
            return latlng.lat >= this._southWest.lat && latlng.lat <= this._northEast.lat &&
                   latlng.lng >= this._southWest.lng && latlng.lng <= this._northEast.lng;
        }
        intersects(other) {
            return !(other._northEast.lat < this._southWest.lat ||
                     other._southWest.lat > this._northEast.lat ||
                     other._northEast.lng < this._southWest.lng ||
                     other._southWest.lng > this._northEast.lng);
        }
        pad(ratio) {
            const latPad = (this._northEast.lat - this._southWest.lat) * ratio;
            const lngPad = (this._northEast.lng - this._southWest.lng) * ratio;
            return new LatLngBounds(
                new LatLng(this._southWest.lat - latPad, this._southWest.lng - lngPad),
                new LatLng(this._northEast.lat + latPad, this._northEast.lng + lngPad)
            );
        }
        toBBoxString() {
            return `${this._southWest.lng},${this._southWest.lat},${this._northEast.lng},${this._northEast.lat}`;
        }
        extend(latlng) {
            const s = Math.min(this._southWest.lat, latlng.lat);
            const w = Math.min(this._southWest.lng, latlng.lng);
            const n = Math.max(this._northEast.lat, latlng.lat);
            const e = Math.max(this._northEast.lng, latlng.lng);
            return new LatLngBounds(new LatLng(s, w), new LatLng(n, e));
        }
        getBounds() { return this; }
    }

    // =====================================================
    // L.Point
    // =====================================================
    class Point {
        constructor(x, y) {
            this.x = parseFloat(x); this.y = parseFloat(y);
        }
        add(p) { return new Point(this.x + p.x, this.y + p.y); }
        subtract(p) { return new Point(this.x - p.x, this.y - p.y); }
        multiplyBy(n) { return new Point(this.x * n, this.y * n); }
        divideBy(n) { return new Point(this.x / n, this.y / n); }
        distanceTo(p) { return Math.sqrt((this.x - p.x)**2 + (this.y - p.y)**2); }
        equals(p) { return this.x === p.x && this.y === p.y; }
    }

    // =====================================================
    // L.GeoJSON (Coordinate utilities)
    // =====================================================
    const GeoJSON = {
        coordsToLatLng: function(coords, reverse) {
            // MapLibre: [lng, lat] → Leaflet: [lat, lng]
            if (reverse) {
                return new LatLng(coords[1], coords[0], coords[2]);
            }
            return new LatLng(coords[0], coords[1], coords[2]);
        },
        coordsToLatLngs: function(coords, levelsDeep, reverse) {
            levelsDeep = levelsDeep || 0;
            if (levelsDeep === 0) {
                return this.coordsToLatLng(coords, reverse !== false);
            }
            const result = [];
            for (let i = 0; i < coords.length; i++) {
                if (levelsDeep === 1) {
                    result.push(this.coordsToLatLng(coords[i], reverse !== false));
                } else {
                    result.push(this.coordsToLatLngs(coords[i], levelsDeep - 1, reverse));
                }
            }
            return result;
        },
        latLngToCoords: function(latlng) {
            return [latlng.lng, latlng.lat];
        },
        latLngsToCoords: function(latlngs, levelsDeep, close) {
            levelsDeep = levelsDeep || 0;
            close = close || false;
            const result = [];
            for (let i = 0; i < latlngs.length; i++) {
                if (levelsDeep === 1) {
                    result.push(this.latLngToCoords(latlngs[i]));
                } else {
                    result.push(this.latLngsToCoords(latlngs[i], levelsDeep - 1, close));
                }
            }
            if (close && levelsDeep > 0 && result.length > 0) {
                const first = levelsDeep === 1 ? this.latLngToCoords(latlngs[0]) : this.latLngsToCoords(latlngs[0], levelsDeep - 1, true);
                const last = result[result.length - 1];
                const firstCoords = levelsDeep === 1 ? first : (Array.isArray(first) ? first[0] : first);
                if (JSON.stringify(firstCoords) !== JSON.stringify(last)) {
                    result.push(firstCoords);
                }
            }
            return result;
        },
        asGeoJSON: function(obj) {
            return obj.toGeoJSON ? obj.toGeoJSON() : obj;
        }
    };

    // =====================================================
    // MapLibreFeatureGroup (replaces L.FeatureGroup)
    // =====================================================
    class MapLibreFeatureGroup {
        constructor() {
            this._layers = [];
            this._map = null;
            this._sourceId = 'fg_source_' + Math.random().toString(36).substr(2, 9);
            this._layerId = 'fg_layer_' + Math.random().toString(36).substr(2, 9);
            this._eventHandlers = {};
        }

        addTo(map) {
            if (map && map instanceof maplibregl.Map) {
                this._map = map;
                this._initSourceAndLayer();
            } else if (map && typeof map.on === 'function') {
                // Leaflet map wrapper
                this._map = map;
            }
            map.addLayer ? null : null;
            return this;
        }

        _initSourceAndLayer() {
            if (!this._map || !this._map.addSource) return;
            try {
                if (this._map.getSource(this._sourceId)) {
                    this._map.removeLayer(this._layerId);
                    this._map.removeSource(this._sourceId);
                }
                this._map.addSource(this._sourceId, {
                    type: 'geojson',
                    data: { type: 'FeatureCollection', features: [] }
                });
                this._map.addLayer({
                    id: this._layerId,
                    type: 'circle',
                    source: this._sourceId,
                    paint: {
                        'circle-radius': 6,
                        'circle-color': '#3388ff',
                        'circle-opacity': 0.8,
                        'circle-stroke-width': 2,
                        'circle-stroke-color': '#ffffff'
                    }
                });
            } catch(e) { /* Source may already exist */ }
        }

        _getGeoJSON() {
            return {
                type: 'FeatureCollection',
                features: this._layers
                    .filter(l => l && l.feature)
                    .map(l => {
                        let geo = l.feature;
                        if (typeof geo === 'function') geo = geo();
                        if (!geo) return null;
                        if (geo.type !== 'Feature' && geo.type !== 'FeatureCollection') {
                            geo = { type: 'Feature', properties: {}, geometry: geo };
                        }
                        return geo;
                    })
                    .filter(Boolean);
            }
        }

        _refreshSource() {
            if (!this._map || !this._map.getSource) return;
            const src = this._map.getSource(this._sourceId);
            if (src && src.setData) {
                src.setData(this._getGeoJSON());
            }
        }

        addLayer(layer) {
            if (!layer) return this;
            this._layers.push(layer);
            this._refreshSource();
            this._emit('layeradd', { layer });
            return this;
        }

        removeLayer(layer) {
            const idx = this._layers.indexOf(layer);
            if (idx !== -1) this._layers.splice(idx, 1);
            this._refreshSource();
            this._emit('layerremove', { layer });
            return this;
        }

        hasLayer(layer) {
            return this._layers.indexOf(layer) !== -1;
        }

        clearLayers() {
            this._layers = [];
            this._refreshSource();
            return this;
        }

        eachLayer(fn) {
            this._layers.forEach(fn);
            return this;
        }

        getLayers() {
            return this._layers.slice();
        }

        getBounds() {
            if (this._layers.length === 0) return new LatLngBounds(
                new LatLng(-90, -180), new LatLng(90, 180)
            );
            let minLat = 90, minLng = 180, maxLat = -90, maxLng = -180;
            this._layers.forEach(l => {
                const geo = l.feature;
                if (!geo || !geo.geometry) return;
                const coords = this._extractCoords(geo.geometry);
                coords.forEach(c => {
                    minLat = Math.min(minLat, c[1]);
                    maxLat = Math.max(maxLat, c[1]);
                    minLng = Math.min(minLng, c[0]);
                    maxLng = Math.max(maxLng, c[0]);
                });
            });
            return new LatLngBounds(new LatLng(minLat, minLng), new LatLng(maxLat, maxLng));
        }

        _extractCoords(geom) {
            if (!geom) return [];
            if (geom.type === 'Point') return [geom.coordinates];
            if (geom.type === 'LineString') return geom.coordinates;
            if (geom.type === 'Polygon') return geom.coordinates[0] || [];
            if (geom.type === 'MultiPoint') return geom.coordinates;
            if (geom.type === 'MultiLineString') return geom.coordinates.flat();
            if (geom.type === 'MultiPolygon') return (geom.coordinates[0] || [])[0] || [];
            return [];
        }

        on(type, fn) {
            if (!this._eventHandlers[type]) this._eventHandlers[type] = [];
            this._eventHandlers[type].push(fn);
            return this;
        }

        off(type, fn) {
            if (!this._eventHandlers[type]) return this;
            if (fn) {
                const idx = this._eventHandlers[type].indexOf(fn);
                if (idx !== -1) this._eventHandlers[type].splice(idx, 1);
            } else {
                this._eventHandlers[type] = [];
            }
            return this;
        }

        _emit(type, data) {
            const handlers = this._eventHandlers[type] || [];
            handlers.forEach(fn => {
                try { fn(data); } catch(e) { console.error('[FeatureGroup]', e); }
            });
        }

        toGeoJSON() { return this._getGeoJSON(); }
    }

    // =====================================================
    // MapLibreLayer (base for L.CircleMarker, L.Marker, etc.)
    // =====================================================
    class MapLibreLayer {
        constructor(latlng, options) {
            this._latlng = latlng;
            this._options = options || {};
            this._map = null;
            this.feature = null;
            this._eventHandlers = {};
        }

        addTo(map) {
            this._map = map;
            this._addToMap();
            return this;
        }

        _addToMap() {
            // Override in subclass
        }

        remove() {
            if (this._map) {
                if (this._mapLayerId) {
                    if (this._map.getLayer) this._map.removeLayer(this._mapLayerId);
                }
                this._map = null;
            }
            return this;
        }

        getLatLng() {
            return this._latlng;
        }

        setLatLng(latlng) {
            this._latlng = latlng;
            this._refresh();
            return this;
        }

        setStyle(options) {
            Object.assign(this._options, options);
            this._refresh();
            return this;
        }

        setPopupContent(content) {
            this._popupContent = content;
            return this;
        }

        bindPopup(content) {
            this._popupContent = content;
            return this;
        }

        openPopup() {
            if (!this._map || !this._popupContent) return;
            new maplibregl.Popup({ closeOnClick: true })
                .setLngLat([this._latlng.lng, this._latlng.lat])
                .setHTML(this._popupContent)
                .addTo(this._map);
        }

        getBounds() {
            return new LatLngBounds(this._latlng, this._latlng);
        }

        toGeoJSON() {
            if (this.feature) {
                if (typeof this.feature === 'function') return this.feature();
                return this.feature;
            }
            return {
                type: 'Feature',
                properties: {},
                geometry: { type: 'Point', coordinates: [this._latlng.lng, this._latlng.lat] }
            };
        }

        on(type, fn) {
            if (!this._eventHandlers[type]) this._eventHandlers[type] = [];
            this._eventHandlers[type].push(fn);
            return this;
        }

        off(type, fn) {
            if (!this._eventHandlers[type]) return this;
            if (fn) {
                const idx = this._eventHandlers[type].indexOf(fn);
                if (idx !== -1) this._eventHandlers[type].splice(idx, 1);
            } else {
                this._eventHandlers[type] = [];
            }
            return this;
        }

        fire(type, data) {
            const handlers = this._eventHandlers[type] || [];
            handlers.forEach(fn => {
                try { fn(data); } catch(e) { console.error('[Layer]', e); }
            });
        }
    }

    // =====================================================
    // L.CircleMarker
    // =====================================================
    class CircleMarker extends MapLibreLayer {
        _addToMap() {
            if (!this._map || !this._map.addLayer) return;
            const id = 'cm_' + Math.random().toString(36).substr(2, 9);
            this._mapLayerId = id;
            const color = this._options.color || '#3388ff';
            const fillColor = this._options.fillColor || color;
            const radius = this._options.radius || 5;
            this._map.addLayer({
                id: id,
                type: 'circle',
                source: undefined,
                paint: {
                    'circle-radius': radius,
                    'circle-color': fillColor,
                    'circle-opacity': this._options.fillOpacity != null ? this._options.fillOpacity : 0.8,
                    'circle-stroke-width': this._options.weight || this._options.strokeWidth || 2,
                    'circle-stroke-color': color
                }
            });
            this._geojsonSourceId = 'cm_src_' + id;
            this._map.addSource(this._geojsonSourceId, {
                type: 'geojson',
                data: this.toGeoJSON()
            });
            // Replace layer source
            this._map.removeLayer(id);
            this._map.addLayer(Object.assign(
                { id: id, source: this._geojsonSourceId },
                { type: 'circle',
                  paint: {
                    'circle-radius': radius,
                    'circle-color': fillColor,
                    'circle-opacity': this._options.fillOpacity != null ? this._options.fillOpacity : 0.8,
                    'circle-stroke-width': this._options.weight || this._options.strokeWidth || 2,
                    'circle-stroke-color': color
                  }
                }
            ));
        }

        toGeoJSON() {
            return {
                type: 'Feature',
                properties: this._options,
                geometry: { type: 'Point', coordinates: [this._latlng.lng, this._latlng.lat] }
            };
        }

        _refresh() {
            this.remove();
            this._addToMap();
        }
    }

    // =====================================================
    // L.Circle (approximated as polygon)
    // =====================================================
    class Circle extends MapLibreLayer {
        constructor(latlng, options) {
            super(latlng, options);
            this._radius = options.radius || options._radius || 100;
        }

        getRadius() { return this._radius; }
        setRadius(r) { this._radius = r; this._refresh(); return this; }

        _getCircleGeo() {
            if (!window.turf) return null;
            return window.turf.circle(
                [this._latlng.lng, this._latlng.lat],
                this._radius,
                { steps: 64, units: 'meters' }
            );
        }

        toGeoJSON() {
            const geo = this._getCircleGeo();
            if (geo) {
                return {
                    type: 'Feature',
                    properties: Object.assign({}, this._options, { _radius: this._radius }),
                    geometry: geo.geometry
                };
            }
            return {
                type: 'Feature',
                properties: Object.assign({}, this._options, { _radius: this._radius }),
                geometry: {
                    type: 'Polygon',
                    coordinates: [[[this._latlng.lng, this._latlng.lat]]]
                }
            };
        }

        getBounds() {
            const geo = this._getCircleGeo();
            if (geo && geo.geometry && geo.geometry.coordinates[0]) {
                const coords = geo.geometry.coordinates[0];
                let minLat=90, minLng=180, maxLat=-90, maxLng=-180;
                coords.forEach(c => {
                    minLat=Math.min(minLat,c[1]); maxLat=Math.max(maxLat,c[1]);
                    minLng=Math.min(minLng,c[0]); maxLng=Math.max(maxLng,c[0]);
                });
                return new LatLngBounds(new LatLng(minLat,minLng), new LatLng(maxLat,maxLng));
            }
            return new LatLngBounds(this._latlng, this._latlng);
        }
    }

    // =====================================================
    // L.Marker
    // =====================================================
    class Marker extends MapLibreLayer {
        constructor(latlng, options) {
            super(latlng, options);
            this._icon = options && options.icon ? options.icon : new DivIcon({});
        }

        setIcon(icon) {
            this._icon = icon;
            this._refresh();
            return this;
        }

        _addToMap() {
            if (!this._map || !this._map.addLayer) return;
            const id = 'mk_' + Math.random().toString(36).substr(2, 9);
            this._mapLayerId = id;

            // Create a custom HTML marker using maplibregl.Marker
            if (typeof maplibregl !== 'undefined' && maplibregl.Marker) {
                const el = document.createElement('div');
                if (this._icon && this._icon.options) {
                    el.className = this._icon.options.className || '';
                    el.innerHTML = this._icon.options.html || '';
                }
                el.style.cursor = 'pointer';

                const marker = new maplibregl.Marker({ element: el, anchor: 'center' })
                    .setLngLat([this._latlng.lng, this._latlng.lat])
                    .addTo(this._map);

                this._mapLayerId_obj = marker;

                if (this._popupContent) {
                    marker.setPopup(new maplibregl.Popup().setHTML(this._popupContent));
                }
            }
        }

        remove() {
            if (this._mapLayerId_obj) {
                this._mapLayerId_obj.remove();
                this._mapLayerId_obj = null;
            }
            this._map = null;
            return this;
        }

        bringToFront() {}
        bringToBack() {}

        toGeoJSON() {
            return {
                type: 'Feature',
                properties: this._options,
                geometry: { type: 'Point', coordinates: [this._latlng.lng, this._latlng.lat] }
            };
        }
    }

    // =====================================================
    // L.DivIcon / L.Icon
    // =====================================================
    class DivIcon {
        constructor(options) {
            this.options = Object.assign({
                className: '',
                html: '',
                iconSize: [20, 20],
                iconAnchor: [10, 10],
                popupAnchor: [0, -10]
            }, options || {});
        }
    }

    class Icon {
        constructor(options) {
            this.options = Object.assign({
                iconUrl: '',
                iconSize: [25, 41],
                iconAnchor: [12, 41],
                popupAnchor: [1, -34]
            }, options || {});
        }
    }

    // =====================================================
    // L.Polyline / L.Polygon
    // =====================================================
    class Polyline extends MapLibreLayer {
        constructor(latlngs, options) {
            super(latlngs && latlngs[0] ? latlngs[0] : new LatLng(0, 0), options);
            this._latlngs = latlngs || [];
        }

        getLatLngs() { return this._latlngs; }
        setLatLngs(l) { this._latlngs = l; this._refresh(); return this; }
        addLatLng(latlng) { this._latlngs.push(latlng); this._refresh(); return this; }

        _getGeoCoords() {
            return this._latlngs.map(ll => [ll.lng, ll.lat]);
        }

        toGeoJSON() {
            const coords = this._getGeoCoords();
            const isPolygon = this instanceof Polygon;
            if (isPolygon && coords.length > 0) coords.push(coords[0]);
            return {
                type: 'Feature',
                properties: this._options,
                geometry: {
                    type: isPolygon ? 'Polygon' : 'LineString',
                    coordinates: isPolygon ? [coords] : coords
                }
            };
        }

        getBounds() {
            if (this._latlngs.length === 0) return new LatLngBounds(
                new LatLng(0, 0), new LatLng(0, 0)
            );
            let minLat=90, minLng=180, maxLat=-90, maxLng=-180;
            this._latlngs.forEach(ll => {
                minLat=Math.min(minLat,ll.lat); maxLat=Math.max(maxLat,ll.lat);
                minLng=Math.min(minLng,ll.lng); maxLng=Math.max(maxLng,ll.lng);
            });
            return new LatLngBounds(new LatLng(minLat,minLng), new LatLng(maxLat,maxLng));
        }
    }

    class Polygon extends Polyline {
        // Polygon inherits from Polyline
    }

    // =====================================================
    // L.Rectangle
    // =====================================================
    class Rectangle extends Polygon {
        constructor(bounds, options) {
            const sw = bounds.getSouthWest ? bounds.getSouthWest() : bounds._southWest;
            const ne = bounds.getNorthEast ? bounds.getNorthEast() : bounds._northEast;
            const latlngs = [
                new LatLng(sw.lat, sw.lng),
                new LatLng(ne.lat, sw.lng),
                new LatLng(ne.lat, ne.lng),
                new LatLng(sw.lat, ne.lng)
            ];
            super(latlngs, options);
        }
    }

    // =====================================================
    // L.geoJSON
    // =====================================================
    function geoJSON(data, options) {
        options = options || {};
        const layers = [];

        function processFeature(feat) {
            const geo = feat.geometry;
            const props = feat.properties || {};

            let latlngs = [];
            let layer = null;

            if (geo.type === 'Point') {
                const ll = new LatLng(geo.coordinates[1], geo.coordinates[0]);
                layer = new Marker(ll, props);
            } else if (geo.type === 'LineString') {
                latlngs = geo.coordinates.map(c => new LatLng(c[1], c[0]));
                layer = new Polyline(latlngs, props);
            } else if (geo.type === 'Polygon') {
                latlngs = (geo.coordinates[0] || []).map(c => new LatLng(c[1], c[0]));
                layer = new Polygon(latlngs, props);
            } else if (geo.type === 'Circle' || props._radius) {
                const center = props._center || geo.coordinates;
                const radius = props._radius || 100;
                layer = new Circle(new LatLng(center[1], center[0]), Object.assign({}, props, { radius }));
            } else if (geo.type === 'MultiPoint') {
                geo.coordinates.forEach(c => {
                    const ll = new LatLng(c[1], c[0]);
                    layers.push(new Marker(ll, props));
                });
                return;
            } else if (geo.type === 'MultiLineString') {
                geo.coordinates.forEach(line => {
                    const lls = line.map(c => new LatLng(c[1], c[0]));
                    layers.push(new Polyline(lls, props));
                });
                return;
            } else if (geo.type === 'MultiPolygon') {
                geo.coordinates.forEach(poly => {
                    const lls = (poly[0] || []).map(c => new LatLng(c[1], c[0]));
                    layers.push(new Polygon(lls, props));
                });
                return;
            }

            if (layer) {
                layer.feature = feat;
                layers.push(layer);
                if (options.onEachFeature) {
                    options.onEachFeature(feat, layer);
                }
            }
        }

        let features = [];
        if (data.type === 'FeatureCollection') {
            features = data.features || [];
        } else if (data.type === 'Feature') {
            features = [data];
        } else if (Array.isArray(data)) {
            features = data;
        }

        features.forEach(processFeature);

        const result = new MapLibreFeatureGroup();
        layers.forEach(l => result.addLayer(l));
        result.getLayers = function() { return layers; };
        result.eachLayer = function(fn) { layers.forEach(fn); return this; };

        return result;
    }

    // =====================================================
    // L.MapLibreGL (Vector tile layer in Leaflet context)
    // =====================================================
    class MapLibreGL {
        constructor(options) {
            this.options = options || {};
            this._map = null;
            this._mlMapInstance = null;
        }
        addTo(map) {
            this._map = map;
            if (map && map._mlMap && this.options && this.options.style) {
                // Load the MapLibre style as a new layer on the existing MapLibre map
                // This replaces the base tiles with the vector style
                map._mlMap.setStyle(this.options.style, { diff: false });
                // After setting new style, optionally set terrain
                if (this.options.pitch !== undefined) {
                    map._mlMap.setPitch(this.options.pitch);
                }
                if (this.options.bearing !== undefined) {
                    map._mlMap.setBearing(this.options.bearing);
                }
            }
            return this;
        }
        remove() {
            this._map = null;
            return this;
        }
        on(type, fn) { return this; }
        off(type, fn) { return this; }
    }

    // Make maplibregl available as L.MapLibreGL.maplibregl for existing code
    MapLibreGL.prototype.maplibregl = typeof maplibregl !== 'undefined' ? maplibregl : null;

    // =====================================================
    // L.Draw.Event (compatibility)
    // =====================================================
    const DrawEvent = {
        CREATED: 'draw:created',
        EDITED: 'draw:edited',
        DELETED: 'draw:deleted',
        DRAWSTART: 'draw:drawstart',
        DRAWSTOP: 'draw:drawstop',
        EDITSTART: 'draw:editstart',
        EDITSTOP: 'draw:editstop'
    };

    // =====================================================
    // L.Edit / L.EditToolbar (stub for edit mode)
    // =====================================================
    const Edit = {
        Marker: function() {},
        Circle: function() {},
        Poly: function() {}
    };

    const EditToolbar = {
        Edit: function() { return { enable: function(){}, disable: function(){}, save: function(){}, revertLayers: function(){} }; },
        Delete: function() { return { enable: function(){}, disable: function(){}, save: function(){}, revertLayers: function(){} }; }
    };

    // =====================================================
    // L.Draw.* (drawing tools)
    // =====================================================
    const Draw = {
        Event: DrawEvent,
        Polyline: function() { this.disable = function(){}; this.enable = function(){}; this.addVertex = function(){}; },
        Polygon: function() { this.disable = function(){}; this.enable = function(){}; },
        Rectangle: function() { this.disable = function(){}; this.enable = function(){}; },
        Circle: function() { this.disable = function(){}; this.enable = function(){}; },
        Marker: function() { this.disable = function(){}; this.enable = function(){}; }
    };

    // =====================================================
    // L.LayerGroup
    // =====================================================
    class LayerGroup extends MapLibreFeatureGroup {
        constructor() { super(); }
    }

    // =====================================================
    // L.Control.* (basic)
    // =====================================================
    class ControlClass {
        constructor(options) {
            this.options = options || {};
            this._container = null;
        }
        addTo(map) {
            if (this.onAdd && map && map._mlMap) {
                this._container = this.onAdd(map);
                if (this._container && map._mlMap.getContainer) {
                    // Append to map container
                    const mapContainer = map._mlMap.getContainer();
                    if (mapContainer && mapContainer.appendChild) {
                        mapContainer.appendChild(this._container);
                    }
                }
            }
            return this;
        }
        getContainer() { return this._container; }
    }

    const Control = {
        layers: function(baseMaps, overlays) {
            return {
                addTo: function() { return this; },
                addOverlay: function() {},
                addBaseLayer: function() {}
            };
        },
        attribution: function(options) {
            return {
                addTo: function(map) {
                    if (map && map._mlMap && maplibregl && maplibregl.AttributionControl) {
                        map._mlMap.addControl(new maplibregl.AttributionControl({ compact: true }), options && options.position || 'bottom-right');
                    }
                    return this;
                }
            };
        }
    };

    // For L.control() factory pattern
    global.L.control = function(options) {
        return new ControlClass(options);
    };

    // =====================================================
    // L.tileLayer / L.tileLayer.wms (MapLibre raster source)
    // =====================================================
    class TileLayerCompat {
        constructor(url, options) {
            this._url = url;
            this._options = options || {};
            this._layerId = null;
            this._sourceId = null;
            this._map = null;
            this.options = this._options;
            this.aot_id = null;
        }

        addTo(map) {
            this._map = map;
            if (map && map._mlMap && map._mlMap.addLayer && map._mlMap.addSource) {
                this._sourceId = 'tile_' + Math.random().toString(36).substr(2, 9);
                this._layerId = 'tile_layer_' + Math.random().toString(36).substr(2, 9);

                let tileUrl = this._url;
                // Replace {s} with a subdomain
                tileUrl = tileUrl.replace('{s}', 'a');

                map._mlMap.addSource(this._sourceId, {
                    type: 'raster',
                    tiles: [tileUrl],
                    tileSize: this._options.tileSize || 256,
                    minzoom: this._options.minZoom || 0,
                    maxzoom: this._options.maxZoom || 19,
                    attribution: this._options.attribution || ''
                });

                map._mlMap.addLayer({
                    id: this._layerId,
                    type: 'raster',
                    source: this._sourceId,
                    paint: {
                        'raster-opacity': this._options.opacity != null ? this._options.opacity : 1.0,
                        'raster-saturation': 0,
                        'raster-contrast': 0
                    },
                    layout: { visibility: 'visible' }
                });
            }
            return this;
        }

        remove() {
            if (this._map && this._map._mlMap) {
                if (this._layerId && this._map._mlMap.getLayer && this._map._mlMap.getLayer(this._layerId)) {
                    this._map._mlMap.removeLayer(this._layerId);
                }
                if (this._sourceId && this._map._mlMap.getSource && this._map._mlMap.getSource(this._sourceId)) {
                    this._map._mlMap.removeSource(this._sourceId);
                }
            }
            this._map = null;
            return this;
        }
    }

    function tileLayer(url, options) {
        return new TileLayerCompat(url, options);
    }

    tileLayer.wms = function(url, options) {
        const layer = new TileLayerCompat(url, Object.assign({ _wms: true }, options));
        layer.addTo = function(map) {
            this._map = map;
            if (map && map._mlMap && map._mlMap.addLayer && map._mlMap.addSource) {
                this._sourceId = 'wms_' + Math.random().toString(36).substr(2, 9);
                this._layerId = 'wms_layer_' + Math.random().toString(36).substr(2, 9);
                map._mlMap.addSource(this._sourceId, {
                    type: 'raster',
                    tiles: [url],
                    tileSize: this._options.tileSize || 256,
                    minzoom: this._options.minZoom || 0,
                    maxzoom: this._options.maxZoom || 19,
                    attribution: this._options.attribution || ''
                });
                map._mlMap.addLayer({
                    id: this._layerId,
                    type: 'raster',
                    source: this._sourceId,
                    paint: { 'raster-opacity': this._options.opacity != null ? this._options.opacity : 1.0 },
                    layout: { visibility: 'visible' }
                });
            }
            return this;
        };
        return layer;
    };

    // =====================================================
    // L.map (MapLibre wrapper with Leaflet API)
    // =====================================================
    class MapClass {
        constructor(id, options) {
            this._id = id;
            this._container = typeof id === 'string' ? document.getElementById(id) : id;
            this._options = options || {};
            this._layers = [];
            this._eventHandlers = {};
            this._eventHandlersById = {};
            this._nextId = 1;
            this._doubleClickZoom = { enabled: () => true, disable: () => {}, enable: () => {} };

            if (typeof maplibregl !== 'undefined' && this._container) {
                // Use MapLibre as the underlying engine
                this._mlMap = new maplibregl.Map({
                    container: this._container,
                    center: options.center || [126.978, 37.566],
                    zoom: options.zoom || 12,
                    maxZoom: options.maxZoom || 22,
                    pitch: options.pitch || 0,
                    bearing: options.bearing || 0,
                    attributionControl: false
                });

                // Sync Leaflet-style events to MapLibre
                const self = this;
                this._mlMap.on('click', (e) => self._emit('click', { latlng: new LatLng(e.lngLat.lat, e.lngLat.lng) }));
                this._mlMap.on('dblclick', (e) => self._emit('dblclick', { latlng: new LatLng(e.lngLat.lat, e.lngLat.lng) }));
                this._mlMap.on('contextmenu', (e) => self._emit('contextmenu', { latlng: new LatLng(e.lngLat.lat, e.lngLat.lng) }));
                this._mlMap.on('zoom', () => self._emit('zoom'));
                this._mlMap.on('move', () => self._emit('move'));
                this._mlMap.on('moveend', () => self._emit('moveend'));
                this._mlMap.on('layeradd', (e) => self._emit('layeradd', { layer: e.layer }));
                this._mlMap.on('overlayadd', (e) => self._emit('overlayadd', { layer: e.layer }));
                this._mlMap.on('overlayremove', (e) => self._emit('overlayremove', { layer: e.layer }));
                this._mlMap.on('resize', () => self._emit('resize'));
            }
        }

        addLayer(layer) {
            this._layers.push(layer);
            if (!layer) return this;
            if (layer instanceof MapLibreGL) {
                // Vector style layer: load on the MapLibre map
                layer.addTo(this);
            } else if (typeof layer.addTo === 'function') {
                layer.addTo(this);
            }
            this._emit('layeradd', { layer });
            return this;
        }

        removeLayer(layer) {
            const idx = this._layers.indexOf(layer);
            if (idx !== -1) this._layers.splice(idx, 1);
            if (layer && typeof layer.remove === 'function') layer.remove();
            return this;
        }

        hasLayer(layer) {
            return this._layers.indexOf(layer) !== -1;
        }

        eachLayer(fn) {
            this._layers.forEach(fn);
            return this;
        }

        getPane(name) {
            if (this._mlMap) {
                const pane = this._mlMap.getContainer();
                return { style: { pointerEvents: 'auto' } };
            }
            return null;
        }

        getContainer() {
            return this._container;
        }

        getCenter() {
            if (this._mlMap) {
                const c = this._mlMap.getCenter();
                return new LatLng(c.lat, c.lng);
            }
            return new LatLng(0, 0);
        }

        getZoom() {
            return this._mlMap ? this._mlMap.getZoom() : 12;
        }

        getBearing() {
            return this._mlMap ? this._mlMap.getBearing() : 0;
        }

        getPitch() {
            return this._mlMap ? this._mlMap.getPitch() : 0;
        }

        setView(center, zoom, options) {
            if (this._mlMap) {
                this._mlMap.jumpTo({ center: [center[1]||center.lng||center.lng, center[0]||center.lat||center.lat], zoom });
            }
            return this;
        }

        setZoom(zoom, options) {
            if (this._mlMap) this._mlMap.setZoom(zoom);
            return this;
        }

        flyToBounds(bounds, options) {
            if (this._mlMap && bounds) {
                const sw = bounds._southWest || bounds.getSouthWest();
                const ne = bounds._northEast || bounds.getNorthEast();
                if (sw && ne) {
                    this._mlMap.fitBounds([[sw.lng, sw.lat], [ne.lng, ne.lat]], options);
                }
            }
            return this;
        }

        fitBounds(bounds, options) { return this.flyToBounds(bounds, options); }

        panTo(latlng, options) {
            if (this._mlMap) this._mlMap.panTo([latlng.lat, latlng.lng]);
            return this;
        }

        setBearing(b) {
            if (this._mlMap) this._mlMap.setBearing(b);
            return this;
        }

        setPitch(p) {
            if (this._mlMap) this._mlMap.setPitch(p);
            return this;
        }

        on(type, idOrFn, fn) {
            if (typeof idOrFn === 'function') {
                // Simple: map.on('click', fn)
                fn = idOrFn;
                if (!this._eventHandlers[type]) this._eventHandlers[type] = [];
                this._eventHandlers[type].push(fn);
            } else {
                // map.on('click', 'marker_id', fn)
                if (!this._eventHandlersById[idOrFn]) this._eventHandlersById[idOrFn] = {};
                if (!this._eventHandlersById[idOrFn][type]) this._eventHandlersById[idOrFn][type] = [];
                this._eventHandlersById[idOrFn][type].push(fn);
            }
            return this;
        }

        off(type, fn) {
            if (!this._eventHandlers[type]) return this;
            if (fn) {
                const idx = this._eventHandlers[type].indexOf(fn);
                if (idx !== -1) this._eventHandlers[type].splice(idx, 1);
            } else {
                this._eventHandlers[type] = [];
            }
            return this;
        }

        _emit(type, data) {
            const handlers = this._eventHandlers[type] || [];
            handlers.forEach(fn => {
                try { fn(data || {}); } catch(e) { console.error('[Map]', e); }
            });
        }

        fire(type, data) { this._emit(type, data); return this; }

        addControl(control) { return this; }
        removeControl(control) { return this; }

        // For AoTMapEditor compatibility
        doubleClickZoom = {
            enabled: () => true,
            disable: () => {},
            enable: () => {}
        };

        // For aoTGeoDesign layer storage
        aotBaseMaps = {};
        aotOverlayMaps = {};
        aotVirtualLayers = [];

        // Expose MapLibre map instance for direct access
        get maplibreMap() { return this._mlMap; }

        getContainer() { return this._container; }
    }

    // =====================================================
    // L.Class (basic stub)
    // =====================================================
    class Class {
        constructor() {}
        addInitHook() {}
    }

    // =====================================================
    // Assemble the L namespace
    // =====================================================
    global.L = {
        // Core classes
        Class: Class,
        Map: MapClass,
        FeatureGroup: MapLibreFeatureGroup,
        LayerGroup: LayerGroup,
        GeoJSON: GeoJSON,
        geoJSON: geoJSON,

        // Layer types
        CircleMarker: CircleMarker,
        Circle: Circle,
        Marker: Marker,
        Polyline: Polyline,
        Polygon: Polygon,
        Rectangle: Rectangle,

        // Icons
        DivIcon: DivIcon,
        Icon: Icon,

        // Utilities
        LatLng: LatLng,
        LatLngBounds: LatLngBounds,
        Point: Point,

        // MapLibre GL bridge
        MapLibreGL: MapLibreGL,

        // Draw events
        Draw: Draw,
        Edit: Edit,
        EditToolbar: EditToolbar,

        // DOM
        DomUtil: DomUtil,
        DomEvent: DomEvent,

        // Controls
        control: Object.assign(function(options) { return new ControlClass(options); }, Control),
        tileLayer: tileLayer,
        control_layers: Control.layers,

        // Version stub
        version: '1.9.0-compat',
        noConflict: function() { return global.L; }
    };

    // Also create L as a function for L.map(id, options)
    global.L.map = function(id, options) {
        return new MapClass(id, options);
    };

    // Also support L.control() factory
    global.L.control = function(options) {
        return new ControlClass(options);
    };

    console.log('[LeafletCompat] Leaflet compatibility layer initialized (MapLibre-backed)');

})(window);
