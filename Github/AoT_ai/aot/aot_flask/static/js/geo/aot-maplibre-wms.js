/**
 * aot-maplibre-wms.js
 * Direct WMS Layer Integration for MapLibre without Bridge
 * 
 * This module provides direct WMS layer support in MapLibre-GL:
 * - VWorld WMS (BaseMap, Satellite) direct integration
 * - Layer toggle visibility control
 * - Opacity adjustment
 * - Multiple WMS layer management
 * 
 * @module AoTWMSManager
 * @version 1.0.0
 * @requires MapLibre-GL
 * 
 * @example
 * // Initialize WMS manager
 * const wms = AoTWMSManager.create(map, {
 *   vworldKey: 'YOUR_VWORLD_KEY'
 * });
 * 
 * @example
 * // Add VWorld BaseMap
 * wms.addVWorldBaseMap();
 * 
 * @example
 * // Add VWorld Satellite
 * wms.addVWorldSatellite();
 * 
 * @example
 * // Toggle layer visibility
 * wms.setLayerVisibility('vworld-base', false);
 * 
 * @example
 * // Adjust opacity
 * wms.setLayerOpacity('vworld-base', 0.5);
 */

(function(global) {
  'use strict';

  /**
   * VWorld WMS Service URLs
   * @constant {Object}
   */
  const VWORLD_WMS = {
    BASE_MAP: {
      url: 'https://api.vworld.kr/req/wms?',
      layers: 'Base',
      styles: 'default',
      format: 'image/png',
      transparent: true,
      crs: 'EPSG:3857'
    },
    SATELLITE: {
      url: 'https://api.vworld.kr/req/wms?',
      layers: 'Satellite',
      styles: 'default',
      format: 'image/png',
      transparent: true,
      crs: 'EPSG:3857'
    },
    HYBRID: {
      url: 'https://api.vworld.kr/req/wms?',
      layers: 'Hybrid',
      styles: 'default',
      format: 'image/png',
      transparent: true,
      crs: 'EPSG:3857'
    },
    CADASTRAL: {
      url: 'https://api.vworld.kr/req/wms?',
      layers: 'LP_PA_CBND_BUBAN,LP_PA_CBDE_BUBAN,LT_CZ_SC_BSNSIGNAGE',
      styles: 'default',
      format: 'image/png',
      transparent: true,
      crs: 'EPSG:3857'
    }
  };

  /**
   * AoT WMS Manager Namespace
   * @namespace AoTWMSManager
   */
  const AoTWMSManager = {
    /** @type {Map<string, WMSInstance>} Active WMS manager instances */
    instances: new Map(),

    /** @type {string} Instance counter */
    _instanceCounter: 0,

    /** @type {Object} VWorld WMS configuration */
    VWORLD_WMS: VWORLD_WMS
  };

  /**
   * WMS Layer Info Class
   * Stores metadata about each WMS layer
   */
  class WMSLayerInfo {
    constructor(id, sourceId, layerId, options) {
      this.id = id;
      this.sourceId = sourceId;
      this.layerId = layerId;
      this.options = Object.assign({}, options);
      this.visible = true;
      this.opacity = options.opacity || 0.8;
    }
  }

  /**
   * WMS Instance Class
   * Manages WMS layers for a single MapLibre map
   */
  class WMSInstance {
    /**
     * Create a new WMS instance
     * @param {maplibregl.Map} map - MapLibre map instance
     * @param {Object} options - Configuration options
     * @param {string} [options.vworldKey='A50259E8-EF6E-11EA-8F8D-E7402F6DAF88'] - VWorld API key
     * @param {string} [options.defaultOpacity=0.8] - Default layer opacity
     * @param {number} [options.tileSize=256] - Tile size for WMS requests
     */
    constructor(map, options = {}) {
      this.id = 'wms_' + (AoTWMSManager._instanceCounter++);
      this.map = map;
      this.vworldKey = options.vworldKey || 'A50259E8-EF6E-11EA-8F8D-E7402F6DAF88';
      this.defaultOpacity = options.defaultOpacity || 0.8;
      this.tileSize = options.tileSize || 256;

      /** @type {Map<string, WMSLayerInfo>} Managed WMS layers */
      this.layers = new Map();

      console.log('[AoTWMSManager] Instance created:', this.id);
    }

    /**
     * Build WMS URL with required parameters
     * @private
     * @param {Object} config - WMS configuration
     * @returns {string} Complete WMS URL template
     */
    _buildWMSUrl(config) {
      const params = new URLSearchParams({
        service: 'WMS',
        version: '1.3.0',
        request: 'GetMap',
        layers: config.layers,
        styles: config.styles || 'default',
        format: config.format || 'image/png',
        transparent: config.transparent !== false,
        width: this.tileSize,
        height: this.tileSize,
        crs: config.crs || 'EPSG:3857',
        exceptions: 'blank',
        apiKey: this.vworldKey
      });

      return config.url + params.toString() + '&bbox={bbox-epsg-3857}';
    }

    /**
     * Generate unique IDs for source and layer
     * @private
     * @param {string} id - Layer identifier
     * @returns {Object} {sourceId, layerId}
     */
    _generateIds(id) {
      return {
        sourceId: 'wms_' + this.id + '_' + id + '_source',
        layerId: 'wms_' + this.id + '_' + id + '_layer'
      };
    }

    /**
     * Add a WMS layer to the map
     * @param {string} id - Unique layer identifier
     * @param {Object} config - WMS configuration
     * @param {string} config.url - WMS service URL
     * @param {string} config.layers - Comma-separated layer names
     * @param {string} [config.format='image/png'] - Image format
     * @param {boolean} [config.transparent=true] - Enable transparency
     * @param {number} [config.opacity] - Layer opacity (0-1)
     * @param {string} [config.attribution] - Layer attribution text
     * @param {Object} [config.paintOptions={}] - Additional paint properties
     * @returns {string} Layer ID
     */
    addLayer(id, config) {
      // Check if layer already exists
      if (this.layers.has(id)) {
        console.warn('[AoTWMSManager] Layer ' + id + ' already exists');
        return this.layers.get(id).layerId;
      }

      const ids = this._generateIds(id);
      const opacity = config.opacity !== undefined ? config.opacity : this.defaultOpacity;

      // Check if source already exists
      if (this.map.getSource(ids.sourceId)) {
        console.warn('[AoTWMSManager] Source ' + ids.sourceId + ' already exists');
        return ids.layerId;
      }

      // Build WMS URL
      const wmsUrl = this._buildWMSUrl(config);

      // Add raster source
      try {
        this.map.addSource(ids.sourceId, {
          type: 'raster',
          tiles: [wmsUrl],
          tileSize: this.tileSize,
          scheme: 'xyz',
          attribution: config.attribution || '© VWorld'
        });

        // Add raster layer
        this.map.addLayer({
          id: ids.layerId,
          type: 'raster',
          source: ids.sourceId,
          paint: Object.assign({
            'raster-opacity': opacity,
            'raster-saturation': 0,
            'raster-contrast': 0,
            'raster-fade-duration': 0
          }, config.paintOptions || {})
        });

        // Store layer info
        const layerInfo = new WMSLayerInfo(id, ids.sourceId, ids.layerId, {
          ...config,
          opacity: opacity
        });
        this.layers.set(id, layerInfo);

        console.log('[AoTWMSManager] Layer added:', id);
        return ids.layerId;

      } catch (e) {
        console.error('[AoTWMSManager] Error adding layer ' + id + ':', e);
        return null;
      }
    }

    /**
     * Add VWorld BaseMap layer
     * @param {string} [id='vworld-base'] - Layer identifier
     * @param {Object} [options={}] - Additional options
     * @returns {string} Layer ID
     */
    addVWorldBaseMap(id = 'vworld-base', options = {}) {
      const config = Object.assign({}, VWORLD_WMS.BASE_MAP, options);
      return this.addLayer(id, config);
    }

    /**
     * Add VWorld Satellite layer
     * @param {string} [id='vworld-satellite'] - Layer identifier
     * @param {Object} [options={}] - Additional options
     * @returns {string} Layer ID
     */
    addVWorldSatellite(id = 'vworld-satellite', options = {}) {
      const config = Object.assign({}, VWORLD_WMS.SATELLITE, options);
      return this.addLayer(id, config);
    }

    /**
     * Add VWorld Hybrid layer
     * @param {string} [id='vworld-hybrid'] - Layer identifier
     * @param {Object} [options={}] - Additional options
     * @returns {string} Layer ID
     */
    addVWorldHybrid(id = 'vworld-hybrid', options = {}) {
      const config = Object.assign({}, VWORLD_WMS.HYBRID, options);
      return this.addLayer(id, config);
    }

    /**
     * Add VWorld Cadastral layer
     * @param {string} [id='vworld-cadastral'] - Layer identifier
     * @param {Object} [options={}] - Additional options
     * @returns {string} Layer ID
     */
    addVWorldCadastral(id = 'vworld-cadastral', options = {}) {
      const config = Object.assign({}, VWORLD_WMS.CADASTRAL, options);
      return this.addLayer(id, config);
    }

    /**
     * Add a generic WMS layer
     * @param {string} id - Layer identifier
     * @param {string} url - WMS service URL
     * @param {string} layers - Layer names
     * @param {Object} [options={}] - Additional options
     * @returns {string} Layer ID
     */
    addWMSLayer(id, url, layers, options = {}) {
      const config = Object.assign({
        url: url,
        layers: layers
      }, options);
      return this.addLayer(id, config);
    }

    /**
     * Remove a WMS layer
     * @param {string} id - Layer identifier
     * @returns {boolean} Success status
     */
    removeLayer(id) {
      const layerInfo = this.layers.get(id);
      if (!layerInfo) {
        console.warn('[AoTWMSManager] Layer ' + id + ' not found');
        return false;
      }

      try {
        if (this.map.getLayer(layerInfo.layerId)) {
          this.map.removeLayer(layerInfo.layerId);
        }
        if (this.map.getSource(layerInfo.sourceId)) {
          this.map.removeSource(layerInfo.sourceId);
        }
        this.layers.delete(id);
        console.log('[AoTWMSManager] Layer removed:', id);
        return true;
      } catch (e) {
        console.error('[AoTWMSManager] Error removing layer ' + id + ':', e);
        return false;
      }
    }

    /**
     * Set layer visibility (toggle)
     * @param {string} id - Layer identifier
     * @param {boolean} visible - Show/hide layer
     * @returns {boolean} Success status
     */
    setLayerVisibility(id, visible) {
      const layerInfo = this.layers.get(id);
      if (!layerInfo) {
        console.warn('[AoTWMSManager] Layer ' + id + ' not found');
        return false;
      }

      try {
        this.map.setLayoutProperty(
          layerInfo.layerId,
          'visibility',
          visible ? 'visible' : 'none'
        );
        layerInfo.visible = visible;
        console.log('[AoTWMSManager] Layer ' + id + ' visibility:', visible);
        return true;
      } catch (e) {
        console.error('[AoTWMSManager] Error setting visibility for ' + id + ':', e);
        return false;
      }
    }

    /**
     * Toggle layer visibility
     * @param {string} id - Layer identifier
     * @returns {boolean} New visibility state
     */
    toggleLayerVisibility(id) {
      const layerInfo = this.layers.get(id);
      if (!layerInfo) {
        console.warn('[AoTWMSManager] Layer ' + id + ' not found');
        return null;
      }

      const newVisibility = !layerInfo.visible;
      this.setLayerVisibility(id, newVisibility);
      return newVisibility;
    }

    /**
     * Set layer opacity
     * @param {string} id - Layer identifier
     * @param {number} opacity - Opacity value (0-1)
     * @returns {boolean} Success status
     */
    setLayerOpacity(id, opacity) {
      const layerInfo = this.layers.get(id);
      if (!layerInfo) {
        console.warn('[AoTWMSManager] Layer ' + id + ' not found');
        return false;
      }

      // Clamp opacity to 0-1 range
      const clampedOpacity = Math.max(0, Math.min(1, opacity));

      try {
        this.map.setPaintProperty(layerInfo.layerId, 'raster-opacity', clampedOpacity);
        layerInfo.opacity = clampedOpacity;
        console.log('[AoTWMSManager] Layer ' + id + ' opacity:', clampedOpacity);
        return true;
      } catch (e) {
        console.error('[AoTWMSManager] Error setting opacity for ' + id + ':', e);
        return false;
      }
    }

    /**
     * Get layer information
     * @param {string} id - Layer identifier
     * @returns {Object|null} Layer info object
     */
    getLayerInfo(id) {
      const layerInfo = this.layers.get(id);
      if (!layerInfo) {
        return null;
      }

      return {
        id: layerInfo.id,
        layerId: layerInfo.layerId,
        sourceId: layerInfo.sourceId,
        visible: layerInfo.visible,
        opacity: layerInfo.opacity,
        options: layerInfo.options
      };
    }

    /**
     * Get all managed layers
     * @returns {Array<Object>} Array of layer info objects
     */
    getAllLayers() {
      const result = [];
      this.layers.forEach(function(info, id) {
        result.push({
          id: info.id,
          layerId: info.layerId,
          sourceId: info.sourceId,
          visible: info.visible,
          opacity: info.opacity
        });
      });
      return result;
    }

    /**
     * Check if a layer exists
     * @param {string} id - Layer identifier
     * @returns {boolean}
     */
    hasLayer(id) {
      return this.layers.has(id);
    }

    /**
     * Get layer visibility state
     * @param {string} id - Layer identifier
     * @returns {boolean|null}
     */
    isLayerVisible(id) {
      const layerInfo = this.layers.get(id);
      return layerInfo ? layerInfo.visible : null;
    }

    /**
     * Get layer opacity
     * @param {string} id - Layer identifier
     * @returns {number|null}
     */
    getLayerOpacity(id) {
      const layerInfo = this.layers.get(id);
      return layerInfo ? layerInfo.opacity : null;
    }

    /**
     * Bring layer to front (increase render order)
     * @param {string} id - Layer identifier
     * @returns {boolean}
     */
    raiseLayer(id) {
      const layerInfo = this.layers.get(id);
      if (!layerInfo) {
        console.warn('[AoTWMSManager] Layer ' + id + ' not found');
        return false;
      }

      try {
        // Get current style
        const style = this.map.getStyle();
        const layers = style.layers;

        // Find layer index
        const layerIndex = layers.findIndex(function(l) {
          return l.id === layerInfo.layerId;
        });

        if (layerIndex === -1 || layerIndex === layers.length - 1) {
          return false; // Already at top or not found
        }

        // Move layer to top
        this.map.moveLayer(layerInfo.layerId);
        console.log('[AoTWMSManager] Layer raised:', id);
        return true;
      } catch (e) {
        console.error('[AoTWMSManager] Error raising layer ' + id + ':', e);
        return false;
      }
    }

    /**
     * Send layer to back (decrease render order)
     * @param {string} id - Layer identifier
     * @param {string} [beforeId] - Layer ID to insert before
     * @returns {boolean}
     */
    lowerLayer(id, beforeId) {
      const layerInfo = this.layers.get(id);
      if (!layerInfo) {
        console.warn('[AoTWMSManager] Layer ' + id + ' not found');
        return false;
      }

      try {
        if (beforeId) {
          const beforeLayerInfo = this.layers.get(beforeId);
          if (beforeLayerInfo) {
            this.map.moveLayer(layerInfo.layerId, beforeLayerInfo.layerId);
          }
        } else {
          this.map.moveLayer(layerInfo.layerId);
        }
        console.log('[AoTWMSManager] Layer lowered:', id);
        return true;
      } catch (e) {
        console.error('[AoTWMSManager] Error lowering layer ' + id + ':', e);
        return false;
      }
    }

    /**
     * Remove all WMS layers
     */
    removeAllLayers() {
      var self = this;
      this.layers.forEach(function(info, id) {
        self.removeLayer(id);
      });
      console.log('[AoTWMSManager] All layers removed');
    }

    /**
     * Destroy the WMS instance
     */
    destroy() {
      this.removeAllLayers();
      this.map = null;
      this.layers.clear();
      AoTWMSManager.instances.delete(this.id);
      console.log('[AoTWMSManager] Instance destroyed:', this.id);
    }
  }

  /**
   * Create a new WMS instance
   * @param {maplibregl.Map} map - MapLibre map instance
   * @param {Object} [options={}] - Configuration options
   * @returns {WMSInstance} WMS instance
   */
  AoTWMSManager.create = function(map, options) {
    if (!map) {
      throw new Error('[AoTWMSManager] MapLibre map instance is required');
    }

    var instance = new WMSInstance(map, options);
    this.instances.set(instance.id, instance);
    return instance;
  };

  /**
   * Get a WMS instance by ID
   * @param {string} id - Instance ID
   * @returns {WMSInstance|null}
   */
  AoTWMSManager.get = function(id) {
    return this.instances.get(id) || null;
  };

  /**
   * Get all active WMS instances
   * @returns {Array<WMSInstance>}
   */
  AoTWMSManager.getAll = function() {
    return Array.from(this.instances.values());
  };

  /**
   * Destroy all WMS instances
   */
  AoTWMSManager.destroyAll = function() {
    this.instances.forEach(function(instance) {
      instance.destroy();
    });
    console.log('[AoTWMSManager] All instances destroyed');
  };

  /**
   * VWorld WMS URL builder helper
   * @param {string} type - WMS type ('Base', 'Satellite', 'Hybrid')
   * @param {string} [key] - VWorld API key
   * @returns {Object} WMS configuration object
   */
  AoTWMSManager.createVWorldConfig = function(type, key) {
    var wmsType = type.charAt(0).toUpperCase() + type.slice(1).toLowerCase();
    if (!VWORLD_WMS[wmsType]) {
      console.warn('[AoTWMSManager] Unknown VWorld type:', type);
      return null;
    }
    return Object.assign({}, VWORLD_WMS[wmsType], {
      apiKey: key || 'A50259E8-EF6E-11EA-8F8D-E7402F6DAF88'
    });
  };

  // Export to global scope
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = AoTWMSManager;
  } else {
    global.AoTWMSManager = AoTWMSManager;
  }

})(typeof window !== 'undefined' ? window : this);
