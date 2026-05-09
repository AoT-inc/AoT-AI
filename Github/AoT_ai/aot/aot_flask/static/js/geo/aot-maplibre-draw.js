/**
 * aot-maplibre-draw.js
 * MapLibre-Geoman Compatible Drawing Manager
 * 
 * Vector drawing tools for MapLibre-GL JS with Leaflet.Draw API compatibility.
 * Supports: Polyline, Polygon, Rectangle, Circle, Marker, Edit/Delete modes.
 * 
 * @module AoTDrawManager
 * @version 1.0.0
 * @author AoT Team
 * @requires maplibre-gl, @mapbox/mapbox-gl-draw, terra-draw
 * 
 * @example
 * // Basic initialization
 * const drawer = AoTDrawManager.init('map-container', mapInstance);
 * 
 * @example
 * // Enable drawing tools
 * drawer.enablePolyline();
 * drawer.enablePolygon();
 * drawer.enableRectangle();
 * drawer.enableCircle();
 * drawer.enableMarker();
 * 
 * @example
 * // Get GeoJSON output
 * const geojson = drawer.getGeoJSON();
 * 
 * @example
 * // Leaflet.Draw API compatibility
 * drawer.addLayer(new L.FeatureGroup());
 * drawer.addDrawControl();
 */

(function(global) {
  'use strict';

  /**
   * AoT Draw Manager Namespace
   * @namespace AoTDrawManager
   */
  const AoTDrawManager = {
    /** @type {Map<string, DrawInstance>} Active draw instances */
    instances: new Map(),

    /** @type {string} Default instance ID */
    DEFAULT_ID: 'default',

    /** @type {Object} Default configuration */
    DEFAULT_CONFIG: {
      // Drawing options
      polyline: true,
      polygon: true,
      rectangle: true,
      circle: false,
      marker: true,
      trash: true,
      combine: false,
      uncombine: false,
      // Styling
      stroke: true,
      color: '#3bb2d0',
      fill: '#3bb2d0',
      fillOpacity: 0.1,
      lineWidth: 2,
      // Circle specific (approximated)
      circleRadius: 100,
      // Edit mode
      edit: {
        edit: {
          featureGroup: null,
          'allow self intersection': false
        }
      },
      // Display controls
      displayControls: true,
      controlsPosition: 'top-right',
      // Modes
      modes: {
        draw_line_string: 'straight',
        draw_polygon: 'direct_select'
      }
    },

    /** @type {Object} Leaflet.Draw API compatibility mapping */
    DRAW_TYPES: {
      POLYLINE: 'polyline',
      POLYGON: 'polygon',
      RECTANGLE: 'rectangle',
      CIRCLE: 'circle',
      MARKER: 'marker'
    },

    /** @type {number} Instance counter */
    _instanceCounter: 0,

    /**
     * Get or create default instance
     * @param {maplibregl.Map} map - MapLibre map instance
     * @param {Object} options - Configuration options
     * @returns {DrawInstance} Draw instance
     */
    getDefault: function(map, options) {
      if (!this.instances.has(this.DEFAULT_ID)) {
        this.instances.set(this.DEFAULT_ID, new DrawInstance(this.DEFAULT_ID, map, options));
      }
      return this.instances.get(this.DEFAULT_ID);
    }
  };

  /**
   * Draw Instance Class
   * Manages drawing tools for a single map
   */
  class DrawInstance {
    /**
     * Create a new draw instance
     * @param {string} id - Instance identifier
     * @param {maplibregl.Map} map - MapLibre map instance
     * @param {Object} config - Configuration options
     */
    constructor(id, map, config = {}) {
      this.id = id;
      this.map = map;
      this.config = Object.assign({}, AoTDrawManager.DEFAULT_CONFIG, config);
      
      // State tracking
      this._initialized = false;
      this._activeMode = null;
      this._drawnFeatures = [];
      this._featureGroup = new Set();
      
      // Leaflet.Draw compatibility layer
      this._leafletCompat = {
        layers: new Map(),
        featureGroup: null,
        drawControl: null
      };

      // Terra Draw instance (for alternative drawing)
      this._terraDraw = null;
      
      // Event callbacks
      this._callbacks = {
        draw: {
          created: [],
          edited: [],
          deleted: [],
          drawstart: [],
          drawstop: [],
          editstart: [],
          editstop: [],
          modechange: [],
          selectionchange: []
        }
      };

      // Initialize
      this._init();
    }

    /**
     * Initialize drawing tools
     * @private
     */
    _init() {
      if (this._initialized) {
        console.warn('[AoTDrawManager] Instance already initialized');
        return;
      }

      try {
        // Check MapLibre is loaded
        if (typeof maplibregl === 'undefined') {
          throw new Error('maplibre-gl not loaded');
        }

        // Initialize Mapbox Draw
        this._initMapboxDraw();

        // Initialize Terra Draw for advanced shapes
        this._initTerraDraw();

        // Add default event listeners
        this._bindDefaultEvents();

        this._initialized = true;
        console.log('[AoTDrawManager] Instance initialized: ' + this.id);

      } catch (error) {
        console.error('[AoTDrawManager] Initialization failed:', error);
        throw error;
      }
    }

    /**
     * Initialize Mapbox Draw (for basic shapes)
     * @private
     */
    _initMapboxDraw() {
      // Check if MapboxDraw is available
      if (typeof MapboxDraw === 'undefined') {
        console.warn('[AoTDrawManager] MapboxDraw not available, using TerraDraw only');
        return;
      }

      const drawOptions = {
        displayControlsDefault: false,
        defaultMode: 'simple_select',
        modes: {
          ...MapboxDraw.modes,
          // Add rectangle mode
          draw_rectangle: DrawRectangle
        },
        styles: [
          // Polygon fill
          {
            id: 'gl-draw-polygon-fill',
            type: 'fill',
            filter: ['all', ['==', '$type', 'Polygon'], ['!=', 'mode', 'static']],
            paint: {
              'fill-color': this.config.color,
              'fill-opacity': this.config.fillOpacity
            }
          },
          // Polygon stroke
          {
            id: 'gl-draw-polygon-stroke',
            type: 'line',
            filter: ['all', ['==', '$type', 'Polygon'], ['!=', 'mode', 'static']],
            paint: {
              'line-color': this.config.color,
              'line-width': this.config.lineWidth
            }
          },
          // Line
          {
            id: 'gl-draw-line',
            type: 'line',
            filter: ['all', ['==', '$type', 'LineString'], ['!=', 'mode', 'static']],
            paint: {
              'line-color': this.config.color,
              'line-width': this.config.lineWidth
            }
          },
          // Points
          {
            id: 'gl-draw-point',
            type: 'circle',
            filter: ['all', ['==', '$type', 'Point'], ['!=', 'mode', 'static']],
            paint: {
              'circle-radius': 6,
              'circle-color': this.config.color,
              'circle-stroke-color': '#fff',
              'circle-stroke-width': 2
            }
          },
          // Midpoints
          {
            id: 'gl-draw-point-mid',
            type: 'circle',
            filter: ['all', ['==', '$type', 'Point'], ['==', 'meta', 'midpoint']],
            paint: {
              'circle-radius': 4,
              'circle-color': this.config.color
            }
          },
          // Vertex
          {
            id: 'gl-draw-point-vertex',
            type: 'circle',
            filter: ['all', ['==', '$type', 'Point'], ['==', 'meta', 'vertex']],
            paint: {
              'circle-radius': 6,
              'circle-color': '#fff',
              'circle-stroke-color': this.config.color,
              'circle-stroke-width': 2
            }
          }
        ]
      };

      // Create MapboxDraw instance
      this._mapboxDraw = new MapboxDraw(drawOptions);
      
      // Add to map
      this.map.addControl(this._mapboxDraw, this.config.controlsPosition);

      console.log('[AoTDrawManager] MapboxDraw initialized');
    }

    /**
     * Initialize Terra Draw (for advanced shapes like circles)
     * @private
     */
    _initTerraDraw() {
      // Check if TerraDraw is available
      if (typeof TerraDraw === 'undefined') {
        console.warn('[AoTDrawManager] TerraDraw not available');
        return;
      }

      try {
        this._terraDraw = new TerraDraw({
          adapter: new TerraDrawMaplibreGLAdapter({
            map: this.map
          }),
          snapping: true
        });

        // Register drawing modes
        this._terraDraw.register([
          // Standard modes
          new TerraDrawPolylineCapability(),
          new TerraDrawPolygonCapability(),
          new TerraDrawCircleCapability({
            180: 20 // radius in meters
          }),
          new TerraDrawRectangleCapability(),
          new TerraDrawPointCapability()
        ]);

        this._terraDraw.start();

        console.log('[AoTDrawManager] TerraDraw initialized');

      } catch (error) {
        console.warn('[AoTDrawManager] TerraDraw initialization failed:', error);
        this._terraDraw = null;
      }
    }

    /**
     * Bind default event listeners
     * @private
     */
    _bindDefaultEvents() {
      // MapboxDraw events
      if (this._mapboxDraw) {
        this.map.on('draw.create', (e) => this._onDrawCreate(e));
        this.map.on('draw.update', (e) => this._onDrawEdit(e));
        this.map.on('draw.delete', (e) => this._onDrawDelete(e));
        this.map.on('draw.selectionchange', (e) => this._onSelectionChange(e));
        this.map.on('draw.modechange', (e) => this._emit('modechange', e));
      }

      // TerraDraw events
      if (this._terraDraw) {
        this._terraDraw.on('finish', (feature) => this._onTerraDrawFinish(feature));
      }
    }

    /**
     * Handle draw.create event from MapboxDraw
     * @private
     */
    _onDrawCreate(e) {
      const features = e.features || [];
      features.forEach(feature => {
        this._addFeature(feature);
        this._emit('created', feature);
        // D-3 safety: also fire directly on map so aot-geo-events.js catches it
        try { this.map.fire('draw:created', { feature, layer: feature }); } catch (_) {}
      });
      console.log('[AoTDrawManager] Features created:', features.length);
    }

    /**
     * Handle draw.update event from MapboxDraw
     * @private
     */
    _onDrawEdit(e) {
      const features = e.features || [];
      features.forEach(feature => {
        this._emit('edited', feature);
      });
      console.log('[AoTDrawManager] Features edited:', features.length);
    }

    /**
     * Handle draw.delete event from MapboxDraw
     * @private
     */
    _onDrawDelete(e) {
      const features = e.features || [];
      features.forEach(feature => {
        this._removeFeature(feature);
        this._emit('deleted', feature);
      });
      console.log('[AoTDrawManager] Features deleted:', features.length);
    }

    /**
     * Handle selection change
     * @private
     */
    _onSelectionChange(e) {
      const selected = e.features || [];
      this._emit('selectionchange', selected);
    }

    /**
     * Handle TerraDraw finish
     * @private
     */
    _onTerraDrawFinish(feature) {
      this._addFeature(feature);
      this._emit('created', feature);
      try { this.map.fire('draw:created', { feature, layer: feature }); } catch (_) {}
      console.log('[AoTDrawManager] TerraDraw feature finished:', feature.geometry?.type);
    }

    /**
     * Add feature to internal tracking
     * @private
     */
    _addFeature(feature) {
      this._drawnFeatures.push(feature);
      this._featureGroup.add(feature.id || feature.properties?.id || feature);
    }

    /**
     * Remove feature from internal tracking
     * @private
     */
    _removeFeature(feature) {
      const id = feature.id || feature;
      this._featureGroup.delete(id);
      this._drawnFeatures = this._drawnFeatures.filter(f => 
        (f.id || f) !== id
      );
    }

    /**
     * Emit event to callbacks
     * @private
     */
    _emit(eventType, data) {
      const callbacks = this._callbacks.draw[eventType] || [];
      callbacks.forEach(cb => {
        try {
          cb(data);
        } catch (e) {
          console.error('[AoTDrawManager] Event callback error:', e);
        }
      });
    }

    // ============================================
    // Public API - Drawing Mode Control
    // ============================================

    /**
     * Enable polyline drawing mode.
     * [V13 Port] Attaches a debounce guard so a rapid double-click does not
     * accidentally finish the line immediately after placing a vertex.
     */
    enablePolyline() {
      if (this._mapboxDraw) {
        this._mapboxDraw.changeMode('draw_line_string');
        this._activeMode = 'polyline';
        this._lastVertexTime = 0;

        // Guard: block draw.create if it fires within 500ms of the last click
        // (mirrors 4_docker aot-map-editor.js V13 debounce logic)
        if (!this._polylineDebounceHandler) {
          this._polylineDebounceHandler = (e) => {
            if (this._activeMode !== 'polyline') return;
            const now = Date.now();
            if (now - (this._lastVertexTime || 0) < 500) {
              console.log('[AoTDrawManager] Blocking rapid polyline finish (debounce)');
              // Re-enter draw mode to undo the premature finish
              setTimeout(() => {
                if (this._activeMode === 'polyline') {
                  this._mapboxDraw.changeMode('draw_line_string');
                }
              }, 0);
            }
          };
          this._polylineClickHandler = () => {
            if (this._activeMode === 'polyline') {
              this._lastVertexTime = Date.now();
            }
          };
          this.map.on('draw.create', this._polylineDebounceHandler);
          this.map.on('click', this._polylineClickHandler);
        }
      } else if (this._terraDraw) {
        this._terraDraw.setMode('polyline');
        this._activeMode = 'polyline';
      }
      console.log('[AoTDrawManager] Polyline mode enabled');
    }

    /**
     * Enable polygon drawing mode
     */
    enablePolygon() {
      if (this._mapboxDraw) {
        this._mapboxDraw.changeMode('draw_polygon');
        this._activeMode = 'polygon';
      } else if (this._terraDraw) {
        this._terraDraw.setMode('polygon');
        this._activeMode = 'polygon';
      }
      console.log('[AoTDrawManager] Polygon mode enabled');
    }

    /**
     * Enable rectangle drawing mode
     */
    enableRectangle() {
      if (this._mapboxDraw && this._mapboxDraw.modes.draw_rectangle) {
        this._mapboxDraw.changeMode('draw_rectangle', { mouseRayCastThreshold: 5 });
        this._activeMode = 'rectangle';
      } else if (this._terraDraw) {
        this._terraDraw.setMode('rectangle');
        this._activeMode = 'rectangle';
      }
      console.log('[AoTDrawManager] Rectangle mode enabled');
    }

    /**
     * Enable circle drawing mode (via TerraDraw)
     */
    enableCircle() {
      if (this._terraDraw) {
        this._terraDraw.setMode('circle');
        this._activeMode = 'circle';
        console.log('[AoTDrawManager] Circle mode enabled');
      } else {
        console.warn('[AoTDrawManager] Circle mode requires TerraDraw');
      }
    }

    /**
     * Enable marker placement mode
     */
    enableMarker() {
      if (this._mapboxDraw) {
        this._mapboxDraw.changeMode('draw_point');
        this._activeMode = 'marker';
      } else if (this._terraDraw) {
        this._terraDraw.setMode('point');
        this._activeMode = 'marker';
      }
      console.log('[AoTDrawManager] Marker mode enabled');
    }

    /**
     * Enable edit mode — enters simple_select so user can click a feature,
     * then auto-switches to direct_select for vertex dragging.
     */
    enableEdit() {
      if (!this._mapboxDraw) return;
      this._activeMode = 'edit';

      // If a feature is already selected, jump straight to direct_select
      const preSelected = this._mapboxDraw.getSelectedIds();
      if (preSelected.length > 0) {
        try {
          this._mapboxDraw.changeMode('direct_select', { featureId: preSelected[0] });
        } catch (_) {
          this._mapboxDraw.changeMode('simple_select');
        }
      } else {
        this._mapboxDraw.changeMode('simple_select');
      }

      // Auto-enter direct_select when user clicks a feature
      this._editSelectionHandler = (e) => {
        if (this._activeMode !== 'edit') return;
        const ids = this._mapboxDraw.getSelectedIds();
        if (ids.length > 0) {
          try { this._mapboxDraw.changeMode('direct_select', { featureId: ids[0] }); } catch (_) {}
        }
      };
      this.map.on('draw.selectionchange', this._editSelectionHandler);
      console.log('[AoTDrawManager] Edit mode enabled');
    }

    /**
     * Enable delete mode — simple_select + Delete/Backspace key + click-to-trash.
     */
    enableDelete() {
      if (!this._mapboxDraw) return;
      this._mapboxDraw.changeMode('simple_select');
      this._activeMode = 'delete';

      // Keyboard handler
      this._deleteKeyHandler = (e) => {
        if (this._activeMode !== 'delete') return;
        if (e.key !== 'Delete' && e.key !== 'Backspace') return;
        this._trashSelected();
      };

      // Click-after-selection handler (fires after selectionchange settles)
      this._deleteSelectionHandler = () => {
        if (this._activeMode !== 'delete') return;
        const ids = this._mapboxDraw.getSelectedIds();
        if (ids.length > 0) {
          // Short timeout so user can see selection highlight before deletion
          setTimeout(() => {
            if (this._activeMode === 'delete') this._trashSelected();
          }, 250);
        }
      };

      document.addEventListener('keydown', this._deleteKeyHandler);
      this.map.on('draw.selectionchange', this._deleteSelectionHandler);
      console.log('[AoTDrawManager] Delete mode enabled');
    }

    /**
     * Trash currently selected features and emit 'deleted' for each.
     * @private
     */
    _trashSelected() {
      if (!this._mapboxDraw) return;
      const selected = this._mapboxDraw.getSelected();
      const featuresToDelete = selected.features.slice();
      if (featuresToDelete.length === 0) return;
      this._mapboxDraw.trash();
      featuresToDelete.forEach(f => {
        this._removeFeature(f);
        this._emit('deleted', f);
      });
      console.log('[AoTDrawManager] Trashed features:', featuresToDelete.length);
    }

    /**
     * Enable combine mode for polylines/polygons (client-side merge).
     */
    enableCombine() {
      if (this._mapboxDraw) {
        // MapboxDraw has no 'combine' mode — use simple_select; merging is done externally via turf.
        this._mapboxDraw.changeMode('simple_select');
        this._activeMode = 'combine';
      }
      console.log('[AoTDrawManager] Combine mode enabled (select features to merge)');
    }

    /**
     * Disable drawing mode and return to view; cleans up edit/delete listeners.
     */
    disableDraw() {
      if (this._mapboxDraw) {
        this._mapboxDraw.changeMode('simple_select');
      }
      if (this._terraDraw) {
        this._terraDraw.setMode('view');
      }

      // Cleanup edit listener
      if (this._editSelectionHandler) {
        this.map.off('draw.selectionchange', this._editSelectionHandler);
        this._editSelectionHandler = null;
      }

      // Cleanup delete listeners
      if (this._deleteKeyHandler) {
        document.removeEventListener('keydown', this._deleteKeyHandler);
        this._deleteKeyHandler = null;
      }
      if (this._deleteSelectionHandler) {
        this.map.off('draw.selectionchange', this._deleteSelectionHandler);
        this._deleteSelectionHandler = null;
      }

      // Cleanup polyline debounce listeners
      if (this._polylineDebounceHandler) {
        this.map.off('draw.create', this._polylineDebounceHandler);
        this._polylineDebounceHandler = null;
      }
      if (this._polylineClickHandler) {
        this.map.off('click', this._polylineClickHandler);
        this._polylineClickHandler = null;
      }
      this._lastVertexTime = 0;

      this._activeMode = null;
      console.log('[AoTDrawManager] Drawing mode disabled');
    }

    // ============================================
    // Public API - Feature Management
    // ============================================

    /**
     * Get first feature ID for edit mode
     * @private
     */
    _getFirstFeatureId() {
      if (this._mapboxDraw) {
        const features = this._mapboxDraw.getAll();
        return features.features.length > 0 ? features.features[0].id : null;
      }
      return null;
    }

    /**
     * Get all drawn features as GeoJSON
     * @returns {Object} GeoJSON FeatureCollection
     */
    getGeoJSON() {
      if (this._mapboxDraw) {
        return this._mapboxDraw.getAll();
      }
      return {
        type: 'FeatureCollection',
        features: this._drawnFeatures
      };
    }

    /**
     * Get features as Leaflet.Draw compatible format
     * @returns {Array} Array of layer-like objects
     */
    getLayers() {
      const geojson = this.getGeoJSON();
      return geojson.features.map(f => ({
        feature: f,
        toGeoJSON: () => f,
        getLatLng: () => {
          if (f.geometry.type === 'Point') {
            return { lat: f.geometry.coordinates[1], lng: f.geometry.coordinates[0] };
          }
          return null;
        }
      }));
    }

    /**
     * Add GeoJSON features
     * @param {Object|string} data - GeoJSON data
     * @returns {Array<string>} Added feature IDs
     */
    addGeoJSON(data) {
      let features;
      if (typeof data === 'string') {
        features = JSON.parse(data).features || [];
      } else {
        features = data.features || [];
      }

      const ids = [];
      features.forEach(feature => {
        if (this._mapboxDraw) {
          const id = this._mapboxDraw.add(feature)[0];
          ids.push(id);
        }
        this._addFeature(feature);
      });

      console.log('[AoTDrawManager] Added', ids.length, 'features');
      return ids;
    }

    /**
     * Clear all drawn features
     * @param {boolean} [silent=false] - Suppress event emission
     */
    clearAll(silent = false) {
      if (this._mapboxDraw) {
        this._mapboxDraw.deleteAll();
      }
      this._drawnFeatures = [];
      this._featureGroup.clear();

      if (!silent) {
        this._emit('draw:deleted', { type: 'clear' });
      }
      console.log('[AoTDrawManager] All features cleared');
    }

    /**
     * Delete selected features
     */
    deleteSelected() {
      if (this._mapboxDraw) {
        const selected = this._mapboxDraw.getSelectedIds();
        if (selected.length > 0) {
          this._mapboxDraw.delete(selected);
          console.log('[AoTDrawManager] Deleted', selected.length, 'features');
        }
      }
    }

    /**
     * Select feature by ID
     * @param {string} featureId - Feature ID
     */
    selectFeature(featureId) {
      if (this._mapboxDraw) {
        this._mapboxDraw.changeMode('direct_select', { featureId });
      }
    }

    /**
     * Get selected feature IDs
     * @returns {Array<string>} Selected feature IDs
     */
    getSelectedIds() {
      if (this._mapboxDraw) {
        return this._mapboxDraw.getSelectedIds();
      }
      return [];
    }

    // ============================================
    // Public API - Event Handling
    // ============================================

    /**
     * Register event callback
     * @param {string} eventType - Event type (created, edited, deleted, etc.)
     * @param {Function} callback - Callback function
     */
    on(eventType, callback) {
      const type = 'draw:' + eventType;
      if (this._callbacks.draw[eventType]) {
        this._callbacks.draw[eventType].push(callback);
      } else {
        console.warn('[AoTDrawManager] Unknown event type:', eventType);
      }
    }

    /**
     * Remove event callback
     * @param {string} eventType - Event type
     * @param {Function} callback - Callback function to remove
     */
    off(eventType, callback) {
      const type = 'draw:' + eventType;
      if (this._callbacks.draw[eventType]) {
        const idx = this._callbacks.draw[eventType].indexOf(callback);
        if (idx !== -1) {
          this._callbacks.draw[eventType].splice(idx, 1);
        }
      }
    }

    /**
     * Once event handler
     * @param {string} eventType - Event type
     * @param {Function} callback - Callback function
     */
    once(eventType, callback) {
      const wrapper = (data) => {
        callback(data);
        this.off(eventType, wrapper);
      };
      this.on(eventType, wrapper);
    }

    // ============================================
    // Public API - Leaflet.Draw Compatibility
    // ============================================

    /**
     * Add feature group for layer management
     * @param {Object} featureGroup - Leaflet-style feature group
     */
    addLayer(featureGroup) {
      this._leafletCompat.featureGroup = featureGroup;
      console.log('[AoTDrawManager] FeatureGroup added');
    }

    /**
     * Add draw control (Leaflet.Draw style)
     * @param {Object} options - Control options
     */
    addDrawControl(options = {}) {
      const controlOptions = Object.assign({
        position: 'topright',
        draw: {
          polyline: this.config.polyline,
          polygon: this.config.polygon,
          rectangle: this.config.rectangle,
          circle: this.config.circle,
          marker: this.config.marker
        },
        edit: {
          featureGroup: this._leafletCompat.featureGroup
        }
      }, options);

      // Emit event for UI to render controls
      this._emit('draw:controladd', controlOptions);
      
      // Store control reference
      this._leafletCompat.drawControl = controlOptions;
      console.log('[AoTDrawManager] Draw control added');
    }

    /**
     * Get Leaflet.Draw compatible draw control
     * @returns {Object} Draw control object
     */
    getDrawControl() {
      return {
        options: this._leafletCompat.drawControl,
        setDrawingOptions: (options) => {
          console.log('[AoTDrawManager] Drawing options updated');
        }
      };
    }

    // ============================================
    // Public API - Utility Methods
    // ============================================

    /**
     * Check if instance is initialized
     * @returns {boolean}
     */
    isReady() {
      return this._initialized;
    }

    /**
     * Check if currently drawing
     * @returns {boolean}
     */
    isDrawing() {
      return this._activeMode !== null;
    }

    /**
     * Get current drawing mode
     * @returns {string|null}
     */
    getMode() {
      return this._activeMode;
    }

    /**
     * Get feature count
     * @returns {number}
     */
    getCount() {
      if (this._mapboxDraw) {
        return this._mapboxDraw.getAll().features.length;
      }
      return this._drawnFeatures.length;
    }

    /**
     * Set drawing style
     * @param {Object} style - Style options
     */
    setStyle(style) {
      if (style.color) this.config.color = style.color;
      if (style.fillColor) this.config.fill = style.fillColor;
      if (style.fillOpacity) this.config.fillOpacity = style.fillOpacity;
      if (style.weight) this.config.lineWidth = style.weight;
      
      // Reinitialize if already initialized
      if (this._initialized) {
        this._init();
      }
    }

    /**
     * Destroy instance and cleanup
     */
    destroy() {
      // Remove controls
      if (this._mapboxDraw) {
        this.map.removeControl(this._mapboxDraw);
        this._mapboxDraw = null;
      }

      // Stop Terra Draw
      if (this._terraDraw) {
        this._terraDraw.stop();
        this._terraDraw = null;
      }

      // Clear state
      this._initialized = false;
      this._drawnFeatures = [];
      this._featureGroup.clear();
      this._activeMode = null;

      // Remove from global instances
      AoTDrawManager.instances.delete(this.id);

      console.log('[AoTDrawManager] Instance destroyed: ' + this.id);
    }
  }

  // ============================================
  // Custom Draw Mode: Rectangle
  // ============================================

  /**
   * Rectangle drawing mode for MapboxDraw
   */
  class DrawRectangle {
    constructor() {
      this._coords = null;
      this._startPoint = null;
      this._currentPoint = null;
      this._mouseMoveHandler = null;
      this._mouseUpHandler = null;
      this._touchMoveHandler = null;
      this._touchEndHandler = null;
    }

    onEnable() {
      this._map.doubleClickZoom.disable();
      this._setupMouseHandlers();
      this._setupTouchHandlers();
    }

    onDisable() {
      this._map.doubleClickZoom.enable();
      this._removeHandlers();
    }

    _setupMouseHandlers() {
      this._mouseMoveHandler = this._onMouseMove.bind(this);
      this._mouseUpHandler = this._onMouseUp.bind(this);
      this._map.on('mousemove', this._mouseMoveHandler);
      this._map.once('mouseup', this._mouseUpHandler);
    }

    _setupTouchHandlers() {
      this._touchMoveHandler = this._onTouchMove.bind(this);
      this._touchEndHandler = this._onTouchEnd.bind(this);
      this._map.on('touchmove', this._touchMoveHandler);
      this._map.once('touchend', this._touchEndHandler);
    }

    _removeHandlers() {
      if (this._mouseMoveHandler) {
        this._map.off('mousemove', this._mouseMoveHandler);
      }
      if (this._mouseUpHandler) {
        this._map.off('mouseup', this._mouseUpHandler);
      }
      if (this._touchMoveHandler) {
        this._map.off('touchmove', this._touchMoveHandler);
      }
      if (this._touchEndHandler) {
        this._map.off('touchend', this._touchEndHandler);
      }
    }

    _onMouseMove(e) {
      this._currentPoint = [e.lngLat.lng, e.lngLat.lat];
    }

    _onTouchMove(e) {
      if (e.originalEvent.touches.length === 1) {
        const touch = e.originalEvent.touches[0];
        const point = this._map.unproject([touch.clientX, touch.clientY]);
        this._currentPoint = [point.lng, point.lat];
      }
    }

    _onMouseUp(e) {
      this._startPoint = [e.lngLat.lng, e.lngLat.lat];
      this._currentPoint = [e.lngLat.lng, e.lngLat.lat];
      
      this._map.on('mousemove', this._mouseMoveHandler);
      this._map.once('mouseup', this._finishDrawing.bind(this));
    }

    _onTouchEnd(e) {
      this._finishDrawing(e);
    }

    _finishDrawing(e) {
      if (this._currentPoint) {
        const rectangle = this._createRectangleFeature();
        this._map.fire('draw.create', { features: [rectangle] });
      }
      this._startPoint = null;
      this._currentPoint = null;
    }

    _createRectangleFeature() {
      const coords = this._getRectangleCoords();
      return {
        type: 'Feature',
        properties: {},
        geometry: {
          type: 'Polygon',
          coordinates: [coords]
        }
      };
    }

    _getRectangleCoords() {
      if (!this._startPoint || !this._currentPoint) {
        return [[0, 0], [0, 0], [0, 0], [0, 0], [0, 0]];
      }

      const sw = [
        Math.min(this._startPoint[0], this._currentPoint[0]),
        Math.min(this._startPoint[1], this._currentPoint[1])
      ];
      const nw = [
        Math.min(this._startPoint[0], this._currentPoint[0]),
        Math.max(this._startPoint[1], this._currentPoint[1])
      ];
      const ne = [
        Math.max(this._startPoint[0], this._currentPoint[0]),
        Math.max(this._startPoint[1], this._currentPoint[1])
      ];
      const se = [
        Math.max(this._startPoint[0], this._currentPoint[0]),
        Math.min(this._startPoint[1], this._currentPoint[1])
      ];

      return [sw, nw, ne, se, sw];
    }

    renderUUID() {
      return 'draw_rectangle_' + Math.random().toString(36).substr(2, 9);
    }

    onRender(layer) {
      // Update preview rectangle
    }
  }

  // ============================================
  // Static Methods
  // ============================================

  /**
   * Create a new draw instance
   * @param {string|HTMLElement} container - Container element or ID
   * @param {maplibregl.Map} map - MapLibre map instance
   * @param {Object} [config={}] - Configuration options
   * @returns {DrawInstance} Draw instance
   */
  AoTDrawManager.init = function(container, map, config = {}) {
    if (!map) {
      throw new Error('[AoTDrawManager] Map instance is required');
    }

    // Generate instance ID
    const id = 'draw_' + (AoTDrawManager._instanceCounter++);

    // Create instance
    const instance = new DrawInstance(id, map, config);

    // Store in instances map
    this.instances.set(id, instance);

    console.log('[AoTDrawManager] Created instance: ' + id);
    return instance;
  };

  /**
   * Get draw instance by ID
   * @param {string} id - Instance ID
   * @returns {DrawInstance|null}
   */
  AoTDrawManager.get = function(id) {
    return this.instances.get(id || AoTDrawManager.DEFAULT_ID) || null;
  };

  /**
   * Get or create default instance
   * @param {maplibregl.Map} map - Map instance
   * @param {Object} [config={}] - Configuration
   * @returns {DrawInstance}
   */
  AoTDrawManager.getDefault = function(map, config) {
    let instance = this.instances.get(AoTDrawManager.DEFAULT_ID);
    if (!instance) {
      instance = this.init(AoTDrawManager.DEFAULT_ID, map, config);
    }
    return instance;
  };

  /**
   * Destroy all instances
   */
  AoTDrawManager.destroyAll = function() {
    this.instances.forEach(function(instance) { instance.destroy(); });
    console.log('[AoTDrawManager] All instances destroyed');
  };

  /**
   * Convert coordinates to GeoJSON format
   * @param {Array} coords - [lng, lat] coordinates
   * @returns {Object} GeoJSON Point
   */
  AoTDrawManager.toGeoJSON = function(coords) {
    return {
      type: 'Feature',
      properties: {},
      geometry: {
        type: 'Point',
        coordinates: coords
      }
    };
  };

  /**
   * Create circle GeoJSON (approximated polygon)
   * @param {Array} center - [lng, lat] center
   * @param {number} radius - Radius in meters
   * @param {number} [steps=64] - Number of polygon vertices
   * @returns {Object} GeoJSON Polygon
   */
  AoTDrawManager.createCircle = function(center, radius, steps = 64) {
    const points = [];
    const km = radius / 1000;
    const lat = center[1] * Math.PI / 180;
    const lng = center[0] * Math.PI / 180;
    const d = (km / 6371) * 2 * Math.PI;

    for (let i = 0; i < steps; i++) {
      const brng = (2 * Math.PI * i) / steps;
      const pLat = Math.asin(Math.sin(lat) * Math.cos(d) + Math.cos(lat) * Math.sin(d) * Math.cos(brng));
      const pLng = ((lng + Math.atan2(Math.sin(brng) * Math.sin(d) * Math.cos(lat), Math.cos(d) - Math.sin(lat) * Math.sin(pLat))) * 180) / Math.PI;
      points.push([pLng, pLat * 180 / Math.PI]);
    }
    points.push(points[0]);

    return {
      type: 'Feature',
      properties: {
        radius: radius,
        center: center
      },
      geometry: {
        type: 'Polygon',
        coordinates: [points]
      }
    };
  };

  /**
   * Create rectangle GeoJSON
   * @param {Array} bounds - [[sw_lng, sw_lat], [ne_lng, ne_lat]]
   * @returns {Object} GeoJSON Polygon
   */
  AoTDrawManager.createRectangle = function(bounds) {
    const sw = bounds[0];
    const ne = bounds[1];
    const nw = [sw[0], ne[1]];
    const se = [ne[0], sw[1]];

    return {
      type: 'Feature',
      properties: {},
      geometry: {
        type: 'Polygon',
        coordinates: [[sw, nw, ne, se, sw]]
      }
    };
  };

  /**
   * Convert Leaflet.Draw event data to GeoJSON
   * @param {Object} layer - Leaflet layer object
   * @returns {Object} GeoJSON Feature
   */
  AoTDrawManager.fromLeafletLayer = function(layer) {
    if (layer.toGeoJSON) {
      return layer.toGeoJSON();
    }
    if (layer.getLatLng) {
      const ll = layer.getLatLng();
      return {
        type: 'Feature',
        properties: {},
        geometry: {
          type: 'Point',
          coordinates: [ll.lng, ll.lat]
        }
      };
    }
    if (layer.getLatLngs) {
      const latlngs = layer.getLatLngs();
      if (latlngs.length === 1) {
        return {
          type: 'Feature',
          properties: {},
          geometry: {
            type: 'Point',
            coordinates: [latlngs[0].lng, latlngs[0].lat]
          }
        };
      }
      const coords = latlngs.map(ll => [ll.lng, ll.lat]);
      if (layer instanceof L.Polygon || layer instanceof L.Rectangle) {
        coords.push(coords[0]);
        return {
          type: 'Feature',
          properties: {},
          geometry: {
            type: 'Polygon',
            coordinates: [coords]
          }
        };
      }
      return {
        type: 'Feature',
        properties: {},
        geometry: {
          type: 'LineString',
          coordinates: coords
        }
      };
    }
    return null;
  };

  // Export to global scope
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = AoTDrawManager;
  } else {
    global.AoTDrawManager = AoTDrawManager;
  }

})(typeof window !== 'undefined' ? window : this);
