/**
 * aot-map-editor.js (LEGACY - DEPRECATED)
 *
 * This file is DEPRECATED. Please use 'aot-map-editor-v2.js' instead.
 *
 * This legacy version uses Leaflet.Draw which is not compatible with MapLibre GL.
 * The v2 version provides full MapLibre Draw support with Leaflet.Draw API compatibility.
 *
 * @deprecated Since GIS Pure MapLibre v5.0
 */

// ============================================================
// LEGACY SHIM - Redirects all calls to v2
// ============================================================

/**
 * AoTMapEditor Legacy Shim
 * Maintains backward compatibility while delegating to v2
 */
const AoTMapEditor = {
    // Reference to v2 implementation
    _v2: null,

    // State
    map: null,
    featureGroup: null,
    drawControl: null,
    editHandler: null,
    deleteHandler: null,
    currentType: 'site',
    editEnabled: false,
    deleteEnabled: false,
    activeDrawer: null,
    activeShape: null,
    _wasDoubleClickZoomEnabled: false,

    styles: {
        site: { color: '#DF5353', weight: 4, fill: false },
        zone: { color: '#28a745', weight: 2, fill: false, dashArray: '5,5' },
        facility: { color: '#82898f', weight: 3, fill: true, fillOpacity: 0.2 },
        equipment: { color: '#007bff', weight: 3, fill: true, fillOpacity: 0.2 },
        aot_device: { color: '#995aff', weight: 2, fill: true, fillOpacity: 0.5 },
        reference: { color: '#ff00ff', weight: 4, dashArray: '10, 10', fill: false, opacity: 1.0 }
    },

    init: function(map, featureGroup) {
        this.map = map;
        this.featureGroup = featureGroup;

        // Check if v2 is available
        if (typeof window.AoTMapEditorV2 !== 'undefined') {
            // Use v2 implementation
            this._v2 = window.AoTMapEditorV2;
            this._v2.init(map, featureGroup);
            console.log('[AoTMapEditor] Legacy shim: Using v2 implementation');
        } else {
            console.warn('[AoTMapEditor] LEGACY: v2 not loaded. Drawing features may be limited.');
        }

        // Apply theme config
        this._applyThemeConfig();

        // Bind legacy events
        this._bindEvents();
    },

    _applyThemeConfig: function() {
        if (!window.AOT_GEO_CONFIG || !window.AOT_GEO_CONFIG.theme_config) return;

        const theme = window.AOT_GEO_CONFIG.theme_config;
        const updateColor = (type, colorKey) => {
            if (theme[colorKey] && this.styles[type]) {
                this.styles[type].color = theme[colorKey];
            }
        };

        updateColor('site', 'site');
        updateColor('zone', 'zone');
        updateColor('facility', 'facility');
        updateColor('equipment', 'equipment');
        updateColor('aot_device', 'device');
    },

    setType: function(type) {
        this.currentType = type;
        if (this._v2) this._v2.setType(type);
        this._triggerStateChange();
    },

    stopAll: function(except = null) {
        if (this._v2) {
            this._v2.stopAll(except);
            this.editEnabled = this._v2.editEnabled;
            this.deleteEnabled = this._v2.deleteEnabled;
            this.activeShape = this._v2.activeShape;
        }
        this._triggerStateChange();
    },

    startDraw: function(shape) {
        if (this._v2) {
            this._v2.startDraw(shape);
            this.activeShape = this._v2.activeShape;
        } else {
            console.warn('[AoTMapEditor] startDraw called but v2 not available');
        }
        this._triggerStateChange();
    },

    toggleEdit: function(force = null) {
        const shouldEnable = (force !== null) ? force : !this.editEnabled;
        if (shouldEnable) this.stopAll('edit');

        if (this._v2) {
            this._v2.toggleEdit(force);
            this.editEnabled = this._v2.editEnabled;
        } else {
            this.editEnabled = shouldEnable;
        }
        this._triggerStateChange();
    },

    toggleDelete: function(force = null) {
        const shouldEnable = (force !== null) ? force : !this.deleteEnabled;
        if (shouldEnable) this.stopAll('delete');

        if (this._v2) {
            this._v2.toggleDelete(force);
            this.deleteEnabled = this._v2.deleteEnabled;
        } else {
            this.deleteEnabled = shouldEnable;
        }
        this._triggerStateChange();
    },

    saveActions: function() {
        if (this._v2) this._v2.saveActions();
        this.editEnabled = false;
        this.deleteEnabled = false;
        this._triggerStateChange();
    },

    cancelActions: function() {
        if (this._v2) this._v2.cancelActions();
        this.editEnabled = false;
        this.deleteEnabled = false;
        this._triggerStateChange();
    },

    markAllDeleted: function() {
        if (this._v2) this._v2.markAllDeleted();
    },

    applyStyle: function(layer, type) {
        if (this.styles[type] && layer.setStyle) {
            layer.setStyle(this.styles[type]);
        }
    },

    clear: function() {
        if (this._v2) this._v2.clear();
        if (this.featureGroup && this.featureGroup.clearLayers) {
            this.featureGroup.clearLayers();
        }
    },

    _bindEvents: function() {
        const self = this;

        // Listen for v2 state changes and sync
        window.addEventListener('aot:editor:state', (e) => {
            if (e.detail) {
                this.editEnabled = e.detail.edit || false;
                this.deleteEnabled = e.detail.delete || false;
                this.activeShape = e.detail.activeShape || null;
            }
        });

        // MapLibre event shims for backward compatibility
        if (this.map) {
            // MapLibre uses 'draw:created' via AoTDrawManager
            // MapLibre uses 'draw:edited' via AoTDrawManager
            // MapLibre uses 'draw:deleted' via AoTDrawManager
            this.map.on('draw:created', (e) => {
                this._triggerCreated(e);
            });
            this.map.on('draw:edited', (e) => {
                this._triggerEdited(e);
            });
            this.map.on('draw:deleted', (e) => {
                this._triggerDeleted(e);
            });
        }
    },

    _triggerCreated: function(e) {
        const event = new CustomEvent('aot:editor:created', {
            detail: {
                layer: e.layer || { feature: e.features?.[0] },
                type: e.layerType || e.features?.[0]?.geometry?.type,
                aotType: this.currentType
            }
        });
        window.dispatchEvent(event);
    },

    _triggerEdited: function(e) {
        const event = new CustomEvent('aot:editor:edited', {
            detail: { layers: e.layers || e.features }
        });
        window.dispatchEvent(event);
    },

    _triggerDeleted: function(e) {
        const event = new CustomEvent('aot:editor:deleted', {
            detail: { layers: e.layers || e.features }
        });
        window.dispatchEvent(event);
    },

    _triggerStateChange: function() {
        const event = new CustomEvent('aot:editor:state', {
            detail: {
                edit: this.editEnabled,
                delete: this.deleteEnabled,
                activeShape: this.activeShape
            }
        });
        window.dispatchEvent(event);
    }
};

// Mark as legacy shim
AoTMapEditor._isLegacy = true;

// Export
window.AoTMapEditor = AoTMapEditor;

// Also expose v2 reference if available
if (typeof window.AoTMapEditorV2 !== 'undefined') {
    window.AoTMapEditor.v2 = window.AoTMapEditorV2;
}
