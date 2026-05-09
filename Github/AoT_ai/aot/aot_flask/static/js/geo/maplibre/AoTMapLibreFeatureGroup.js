/**
 * AoTMapLibreFeatureGroup.js
 * Leaflet.FeatureGroup 호환 - 여러 레이어를 그룹으로 관리
 */
(function(global) {
    'use strict';

    class AoTMapLibreFeatureGroup {
        constructor() {
            this._layers = new Map();
            this._map = null;
            this._eventHandlers = {};
        }

        addLayer(layer) {
            const id = layer._sourceId || layer.id || 'layer-' + Date.now();
            this._layers.set(id, layer);
            if (this._map && layer.addTo) layer.addTo(this._map);
            return this;
        }

        removeLayer(layer) {
            const id = layer._sourceId || layer.id;
            if (this._layers.has(id)) {
                const l = this._layers.get(id);
                if (l.remove) l.remove();
                this._layers.delete(id);
            }
            return this;
        }

        clearLayers() {
            this._layers.forEach(layer => { if (layer.remove) layer.remove(); });
            this._layers.clear();
            return this;
        }

        getLayers() { return Array.from(this._layers.values()); }
        getLayer(id) { return this._layers.get(id) || null; }

        addTo(map) {
            this._map = map;
            this._layers.forEach(layer => { if (layer.addTo) layer.addTo(map); });
            return this;
        }

        eachLayer(callback) {
            this._layers.forEach((layer, id) => callback(layer, id));
            return this;
        }

        getBounds() {
            const bounds = [];
            this._layers.forEach(layer => {
                if (layer.getBounds) {
                    const b = layer.getBounds();
                    if (b && b.isValid && b.isValid()) bounds.push(b);
                }
            });
            if (bounds.length === 0) return null;
            let minLng = Infinity, minLat = Infinity, maxLng = -Infinity, maxLat = -Infinity;
            bounds.forEach(b => {
                const sw = b.getSouthWest(), ne = b.getNorthEast();
                minLng = Math.min(minLng, sw.lng); maxLng = Math.max(maxLng, ne.lng);
                minLat = Math.min(minLat, sw.lat); maxLat = Math.max(maxLat, ne.lat);
            });
            return {
                _southWest: { lat: minLat, lng: minLng },
                _northEast: { lat: maxLat, lng: maxLng },
                getSouthWest: function() { return this._southWest; },
                getNorthEast: function() { return this._northEast; },
                isValid: function() { return minLng !== Infinity; }
            };
        }

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
                    try { handler(data); } catch (e) { console.error('[AoTMapLibreFeatureGroup]', e); }
                });
            }
            return this;
        }

        toGeoJSON() {
            const features = [];
            this._layers.forEach(layer => {
                if (layer.toGeoJSON) {
                    const data = layer.toGeoJSON();
                    if (data && data.features) features.push(...data.features);
                }
            });
            return { type: 'FeatureCollection', features: features };
        }

        remove() { this.clearLayers(); this._map = null; }
    }

    global.AoTMapLibreFeatureGroup = AoTMapLibreFeatureGroup;
})(typeof window !== 'undefined' ? window : global);
