/**
 * AoTMapLibreCompat.js
 * MapLibre GL를 Leaflet 스타일로 추상화하는 호환 레이어
 * Provides Leaflet-compatible API for GeoJSON layers
 */
(function(global) {
    'use strict';

    class AoTMapLibreCompat {
        constructor(geojson, options = {}) {
            this._geojson = geojson;
            this._options = options;
            this._map = null;
            this._sourceId = null;
            this._layerIds = [];
            this._eventHandlers = {};
            this._popup = null;
            this._popupContent = null;
        }

        addTo(map) {
            this._map = map;
            this._addSource();
            this._addLayers();
            this._bindEvents();
            return this;
        }

        _addSource() {
            const id = 'aot-compat-source-' + Date.now();
            this._sourceId = id;
            this._map.addSource(id, {
                type: 'geojson',
                data: this._geojson,
                promoteId: 'id'
            });
        }

        _addLayers() {
            const colors = this._options.colors || { fill: '#995aff', stroke: '#995aff', circle: '#995aff' };
            
            // Fill layer for polygons
            if (this._hasGeometryType('Polygon')) {
                const fillId = this._sourceId + '-fill';
                this._layerIds.push(fillId);
                this._map.addLayer({
                    id: fillId,
                    type: 'fill',
                    source: this._sourceId,
                    filter: ['==', '$type', 'Polygon'],
                    paint: { 'fill-color': colors.fill, 'fill-opacity': this._options.fillOpacity || 0.2 }
                });
                const strokeId = this._sourceId + '-stroke';
                this._layerIds.push(strokeId);
                this._map.addLayer({
                    id: strokeId,
                    type: 'line',
                    source: this._sourceId,
                    filter: ['==', '$type', 'Polygon'],
                    paint: { 'line-color': colors.stroke, 'line-width': this._options.weight || 2 }
                });
            }

            // Line layer for LineStrings
            if (this._hasGeometryType('LineString')) {
                const lineId = this._sourceId + '-line';
                this._layerIds.push(lineId);
                this._map.addLayer({
                    id: lineId,
                    type: 'line',
                    source: this._sourceId,
                    filter: ['==', '$type', 'LineString'],
                    paint: { 'line-color': colors.stroke, 'line-width': this._options.weight || 2 }
                });
            }

            // Circle layer for points
            if (this._hasGeometryType('Point')) {
                const circleId = this._sourceId + '-circle';
                this._layerIds.push(circleId);
                this._map.addLayer({
                    id: circleId,
                    type: 'circle',
                    source: this._sourceId,
                    filter: ['==', '$type', 'Point'],
                    paint: {
                        'circle-color': colors.circle,
                        'circle-radius': this._options.radius || 6,
                        'circle-stroke-width': 2,
                        'circle-stroke-color': '#fff'
                    }
                });
            }
        }

        _hasGeometryType(type) {
            if (!this._geojson || !this._geojson.features) return false;
            return this._geojson.features.some(f => f.geometry && f.geometry.type === type);
        }

        _bindEvents() {
            if (!this._map) return;
            
            this._map.on('click', (e) => {
                const features = this._map.queryRenderedFeatures(e.point, { layers: this._layerIds });
                if (features.length > 0) {
                    this.fire('click', {
                        layer: this,
                        feature: features[0],
                        latlng: e.lngLat ? { lat: e.lngLat.lat, lng: e.lngLat.lng } : null
                    });
                    
                    // Show popup if bound
                    if (this._popupContent) {
                        if (this._popup) this._popup.remove();
                        const feature = features[0];
                        const content = typeof this._popupContent === 'function' ? this._popupContent(feature) : this._popupContent;
                        this._popup = new maplibregl.Popup({ closeButton: true, closeOnClick: true })
                            .setLngLat(e.lngLat)
                            .setHTML(content)
                            .addTo(this._map);
                    }
                }
            });
        }

        // Leaflet-compatible API
        toGeoJSON() { return this._geojson; }
        
        setGeoJSON(geojson) {
            this._geojson = geojson;
            if (this._sourceId) {
                const source = this._map.getSource(this._sourceId);
                if (source) source.setData(geojson);
            }
        }

        getBounds() {
            if (!this._geojson || !this._geojson.features || this._geojson.features.length === 0) return null;
            let minLng = Infinity, minLat = Infinity;
            let maxLng = -Infinity, maxLat = -Infinity;
            const processCoords = (coords) => {
                if (typeof coords[0] === 'number') {
                    minLng = Math.min(minLng, coords[0]);
                    maxLng = Math.max(maxLng, coords[0]);
                    minLat = Math.min(minLat, coords[1]);
                    maxLat = Math.max(maxLat, coords[1]);
                } else {
                    coords.forEach(processCoords);
                }
            };
            this._geojson.features.forEach(f => {
                if (f.geometry && f.geometry.coordinates) {
                    processCoords(f.geometry.coordinates);
                }
            });
            return {
                _southWest: { lat: minLat, lng: minLng },
                _northEast: { lat: maxLat, lng: maxLng },
                getSouthWest: function() { return this._southWest; },
                getNorthEast: function() { return this._northEast; },
                isValid: function() { return minLng !== Infinity; }
            };
        }

        remove() {
            if (this._map) {
                this._layerIds.forEach(id => {
                    if (this._map.getLayer(id)) this._map.removeLayer(id);
                });
                if (this._map.getSource(this._sourceId)) this._map.removeSource(this._sourceId);
            }
            this._map = null;
        }

        // Popup methods
        bindPopup(content) {
            this._popupContent = content;
            return this;
        }

        openPopup(latlng, content) {
            if (this._popup) this._popup.remove();
            this._popup = new maplibregl.Popup()
                .setLngLat([latlng.lng, latlng.lat])
                .setHTML(content)
                .addTo(this._map);
        }

        closePopup() {
            if (this._popup) { this._popup.remove(); this._popup = null; }
        }

        bindTooltip(content, options) { return this; }

        // Event methods
        on(eventType, handler) {
            if (!this._eventHandlers[eventType]) this._eventHandlers[eventType] = [];
            this._eventHandlers[eventType].push(handler);
            return this;
        }

        off(eventType, handler) {
            if (this._eventHandlers[eventType]) {
                this._eventHandlers[eventType] = this._eventHandlers[eventType].filter(h => h !== handler);
            }
            return this;
        }

        fire(eventType, data) {
            if (this._eventHandlers[eventType]) {
                this._eventHandlers[eventType].forEach(handler => {
                    try { handler(data); } catch (e) { console.error('[AoTMapLibreCompat]', e); }
                });
            }
            return this;
        }

        eachLayer(callback) {
            if (this._geojson && this._geojson.features) {
                this._geojson.features.forEach((feature, index) => callback(feature, index));
            }
        }

        setStyle(style) {
            if (style.color) {
                this._layerIds.forEach(id => {
                    if (this._map.getLayer(id)) {
                        if (id.endsWith('-fill')) this._map.setPaintProperty(id, 'fill-color', style.color);
                        else this._map.setPaintProperty(id, 'line-color', style.color);
                    }
                });
            }
        }
    }

    global.AoTMapLibreCompat = AoTMapLibreCompat;
})(typeof window !== 'undefined' ? window : global);
