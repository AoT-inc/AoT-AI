/**
 * aot-vector-layer-manager.js
 * Vector Layer Manager for AoT Map System
 * Manages multiple vector sources and layers with MapLibre-GL
 * 
 * @version 1.0.0
 * @requires maplibre-gl (loaded from CDN or bundled)
 * @namespace AoTVectorLayerManager
 */

(function(window) {
    'use strict';

    /**
     * AoTVectorLayerManager
     * Manages vector tile sources, GeoJSON layers, and styles
     * 
     * @param {Object} map - MapLibre-GL map instance
     * @param {Object} options - Configuration options
     */
    var AoTVectorLayerManager = function(map, options) {
        this.map = map;
        this.options = Object.assign({}, this._getDefaultOptions(), options);
        
        // Source and layer registries
        this.sources = new Map();
        this.layers = new Map();
        this.eventHandlers = new Map();
        
        // Default styles for AoT features
        this.defaultStyles = this._loadDefaultStyles();
        
        // Cursor state
        this._interactiveLayers = new Set();
        
        // Bind methods
        this._onClick = this._onClick.bind(this);
        this._onMouseEnter = this._onMouseEnter.bind(this);
        this._onMouseLeave = this._onMouseLeave.bind(this);
    };

    /**
     * Default configuration options
     * @private
     */
    AoTVectorLayerManager.prototype._getDefaultOptions = function() {
        return {
            clickTolerance: 3,
            cursorOnHover: true,
            defaultLanguage: 'ko'
        };
    };

    /**
     * Load default AoT layer styles
     * @private
     */
    AoTVectorLayerManager.prototype._loadDefaultStyles = function() {
        return {
            // Device markers (point features)
            device: {
                type: 'symbol',
                layout: {
                    'icon-image': ['coalesce', ['get', 'icon'], 'marker-icon'],
                    'icon-size': 1.0,
                    'icon-allow-overlap': true,
                    'text-field': ['get', 'name'],
                    'text-font': ['Noto Sans Regular'],
                    'text-offset': [0, 1.5],
                    'text-anchor': 'top',
                    'text-optional': true
                },
                paint: {
                    'text-color': '#333333',
                    'text-halo-color': '#ffffff',
                    'text-halo-width': 2,
                    'text-opacity': 1
                }
            },
            
            // Facility boundaries (polygon features)
            facility: {
                type: 'fill',
                paint: {
                    'fill-color': '#82898f',
                    'fill-opacity': 0.15
                }
            },
            facilityOutline: {
                type: 'line',
                paint: {
                    'line-color': '#82898f',
                    'line-width': 2,
                    'line-opacity': 0.8
                }
            },
            
            // Zone boundaries (polygon features)
            zone: {
                type: 'fill',
                paint: {
                    'fill-color': '#28a745',
                    'fill-opacity': 0.1
                }
            },
            zoneOutline: {
                type: 'line',
                paint: {
                    'line-color': '#28a745',
                    'line-width': 2,
                    'line-dasharray': [3, 2],
                    'line-opacity': 0.9
                }
            },
            
            // Site boundaries (polygon features)
            site: {
                type: 'fill',
                paint: {
                    'fill-color': '#DF5353',
                    'fill-opacity': 0.1
                }
            },
            siteOutline: {
                type: 'line',
                paint: {
                    'line-color': '#DF5353',
                    'line-width': 3,
                    'line-opacity': 1
                }
            },
            
            // Equipment areas (polygon features)
            equipment: {
                type: 'fill',
                paint: {
                    'fill-color': '#007bff',
                    'fill-opacity': 0.15
                }
            },
            equipmentOutline: {
                type: 'line',
                paint: {
                    'line-color': '#007bff',
                    'line-width': 2,
                    'line-opacity': 0.8
                }
            },
            
            // Reference layers (polygon features)
            reference: {
                type: 'fill',
                paint: {
                    'fill-color': '#ff00ff',
                    'fill-opacity': 0.1
                }
            },
            referenceOutline: {
                type: 'line',
                paint: {
                    'line-color': '#ff00ff',
                    'line-width': 2,
                    'line-dasharray': [5, 3],
                    'line-opacity': 0.8
                }
            },
            
            // Generic polygon styles
            polygon: {
                type: 'fill',
                paint: {
                    'fill-color': ['get', 'color'] || '#888888',
                    'fill-opacity': 0.3
                }
            },
            polygonOutline: {
                type: 'line',
                paint: {
                    'line-color': ['get', 'strokeColor'] || '#333333',
                    'line-width': 2
                }
            },
            
            // Generic line styles
            line: {
                type: 'line',
                paint: {
                    'line-color': ['get', 'color'] || '#007bff',
                    'line-width': ['get', 'width'] || 3,
                    'line-opacity': 0.9
                }
            },
            
            // Point/Circle markers
            circle: {
                type: 'circle',
                paint: {
                    'circle-radius': ['get', 'radius'] || 6,
                    'circle-color': ['get', 'color'] || '#007bff',
                    'circle-opacity': 0.9,
                    'circle-stroke-width': 2,
                    'circle-stroke-color': '#ffffff'
                }
            },
            
            // Heatmap style
            heatmap: {
                type: 'heatmap',
                paint: {
                    'heatmap-weight': ['get', 'weight'] || 1,
                    'heatmap-intensity': 1,
                    'heatmap-color': [
                        'interpolate',
                        ['linear'],
                        ['heatmap-density'],
                        0, 'rgba(0,0,0,0)',
                        0.2, 'rgb(0,0,255)',
                        0.4, 'rgb(0,255,0)',
                        0.6, 'rgb(255,255,0)',
                        0.8, 'rgb(255,128,0)',
                        1, 'rgb(255,0,0)'
                    ],
                    'heatmap-radius': 30,
                    'heatmap-opacity': 0.8
                }
            }
        };
    };

    // ========================================
    // Source Management
    // ========================================

    /**
     * Add a vector tile source to the map
     * @param {string} id - Unique source identifier
     * @param {Object} options - Source options
     * @param {Array} options.tiles - Array of tile URLs
     * @param {number} [options.minzoom=0] - Minimum zoom level
     * @param {number} [options.maxzoom=14] - Maximum zoom level
     * @param {string} [options.attribution=''] - Attribution text
     * @returns {AoTVectorLayerManager} Returns this for chaining
     */
    AoTVectorLayerManager.prototype.addVectorSource = function(id, options) {
        if (!id || !options || !options.tiles) {
            console.error('[AoTVectorLayerManager] Invalid source configuration:', id);
            return this;
        }

        if (this.sources.has(id)) {
            console.warn('[AoTVectorLayerManager] Source already exists:', id);
            return this;
        }

        var sourceConfig = {
            type: 'vector',
            tiles: options.tiles,
            minzoom: options.minzoom || 0,
            maxzoom: options.maxzoom || 14,
            attribution: options.attribution || ''
        };

        try {
            this.map.addSource(id, sourceConfig);
            this.sources.set(id, {
                type: 'vector',
                config: sourceConfig,
                layers: []
            });
            console.log('[AoTVectorLayerManager] Vector source added:', id);
        } catch (e) {
            console.error('[AoTVectorLayerManager] Failed to add source:', id, e);
        }

        return this;
    };

    /**
     * Add a GeoJSON source to the map
     * @param {string} id - Unique source identifier
     * @param {Object|string} data - GeoJSON object or URL
     * @param {Object} [options] - Additional source options
     * @param {boolean} [options.cluster=false] - Enable clustering
     * @param {number} [options.clusterRadius=50] - Cluster radius
     * @param {number} [options.clusterMaxZoom=14] - Max zoom for clustering
     * @returns {AoTVectorLayerManager} Returns this for chaining
     */
    AoTVectorLayerManager.prototype.addGeoJSONSource = function(id, data, options) {
        options = options || {};

        if (!id) {
            console.error('[AoTVectorLayerManager] Source ID required');
            return this;
        }

        if (this.sources.has(id)) {
            console.warn('[AoTVectorLayerManager] Source already exists:', id);
            return this;
        }

        var sourceConfig = {
            type: 'geojson',
            data: data
        };

        // Enable clustering if requested
        if (options.cluster) {
            sourceConfig.cluster = true;
            sourceConfig.clusterRadius = options.clusterRadius || 50;
            sourceConfig.clusterMaxZoom = options.clusterMaxZoom || 14;
            sourceConfig.clusterProperties = options.clusterProperties || {};
        }

        try {
            this.map.addSource(id, sourceConfig);
            this.sources.set(id, {
                type: 'geojson',
                config: sourceConfig,
                layers: [],
                clustered: options.cluster || false
            });
            console.log('[AoTVectorLayerManager] GeoJSON source added:', id);
        } catch (e) {
            console.error('[AoTVectorLayerManager] Failed to add GeoJSON source:', id, e);
        }

        return this;
    };

    /**
     * Update GeoJSON source data
     * @param {string} id - Source ID
     * @param {Object} data - New GeoJSON data
     * @returns {AoTVectorLayerManager}
     */
    AoTVectorLayerManager.prototype.updateGeoJSONData = function(id, data) {
        var source = this.sources.get(id);
        if (!source || source.type !== 'geojson') {
            console.warn('[AoTVectorLayerManager] GeoJSON source not found:', id);
            return this;
        }

        try {
            this.map.getSource(id).setData(data);
            console.log('[AoTVectorLayerManager] GeoJSON data updated:', id);
        } catch (e) {
            console.error('[AoTVectorLayerManager] Failed to update GeoJSON:', id, e);
        }

        return this;
    };

    /**
     * Remove a source and all associated layers
     * @param {string} id - Source ID
     * @returns {AoTVectorLayerManager}
     */
    AoTVectorLayerManager.prototype.removeSource = function(id) {
        var source = this.sources.get(id);
        if (!source) {
            console.warn('[AoTVectorLayerManager] Source not found:', id);
            return this;
        }

        // Remove all associated layers first
        source.layers.forEach(function(layerId) {
            this.removeLayer(layerId);
        }, this);

        try {
            this.map.removeSource(id);
            this.sources.delete(id);
            console.log('[AoTVectorLayerManager] Source removed:', id);
        } catch (e) {
            console.error('[AoTVectorLayerManager] Failed to remove source:', id, e);
        }

        return this;
    };

    /**
     * Get source information
     * @param {string} id - Source ID
     * @returns {Object|null}
     */
    AoTVectorLayerManager.prototype.getSource = function(id) {
        return this.sources.get(id) || null;
    };

    // ========================================
    // Layer Management
    // ========================================

    /**
     * Add a layer to the map
     * @param {Object} layerConfig - Layer configuration
     * @param {string} layerConfig.id - Unique layer identifier
     * @param {string} layerConfig.sourceId - Source ID to use
     * @param {string} [layerConfig.sourceLayer] - Source layer name (for vector tiles)
     * @param {string} [layerConfig.type='symbol'] - Layer type (fill, line, symbol, circle, heatmap)
     * @param {Object} [layerConfig.paint] - Paint properties
     * @param {Object} [layerConfig.layout] - Layout properties
     * @param {Array} [layerConfig.filter] - Layer filter
     * @param {number} [layerConfig.minzoom] - Minimum zoom
     * @param {number} [layerConfig.maxzoom] - Maximum zoom
     * @param {string} [layerConfig.styleType] - Use preset style (device, facility, zone, etc.)
     * @returns {AoTVectorLayerManager}
     */
    AoTVectorLayerManager.prototype.addLayer = function(layerConfig) {
        if (!layerConfig || !layerConfig.id || !layerConfig.sourceId) {
            console.error('[AoTVectorLayerManager] Invalid layer configuration');
            return this;
        }

        if (this.layers.has(layerConfig.id)) {
            console.warn('[AoTVectorLayerManager] Layer already exists:', layerConfig.id);
            return this;
        }

        var source = this.sources.get(layerConfig.sourceId);
        if (!source) {
            console.error('[AoTVectorLayerManager] Source not found:', layerConfig.sourceId);
            return this;
        }

        // Build layer configuration
        var layer = {
            id: layerConfig.id,
            source: layerConfig.sourceId,
            type: layerConfig.type || 'symbol'
        };

        // Add source layer for vector tiles
        if (layerConfig.sourceLayer) {
            layer['source-layer'] = layerConfig.sourceLayer;
        }

        // Apply preset style if specified
        var styleType = layerConfig.styleType;
        if (styleType && this.defaultStyles[styleType]) {
            var presetStyle = this.defaultStyles[styleType];
            layer.layout = Object.assign({}, presetStyle.layout || {}, layerConfig.layout || {});
            layer.paint = Object.assign({}, presetStyle.paint || {}, layerConfig.paint || {});
        } else {
            layer.layout = layerConfig.layout || {};
            layer.paint = layerConfig.paint || {};
        }

        // Apply filter if specified
        if (layerConfig.filter) {
            layer.filter = layerConfig.filter;
        }

        // Apply zoom range
        if (layerConfig.minzoom !== undefined) {
            layer.minzoom = layerConfig.minzoom;
        }
        if (layerConfig.maxzoom !== undefined) {
            layer.maxzoom = layerConfig.maxzoom;
        }

        try {
            this.map.addLayer(layer);
            
            this.layers.set(layerConfig.id, {
                config: layerConfig,
                layer: layer,
                sourceId: layerConfig.sourceId
            });
            
            source.layers.push(layerConfig.id);
            
            // Register for click/hover events if interactive
            if (layerConfig.interactive !== false) {
                this._registerInteractiveLayer(layerConfig.id);
            }
            
            console.log('[AoTVectorLayerManager] Layer added:', layerConfig.id);
        } catch (e) {
            console.error('[AoTVectorLayerManager] Failed to add layer:', layerConfig.id, e);
        }

        return this;
    };

    /**
     * Remove a layer from the map
     * @param {string} id - Layer ID
     * @returns {AoTVectorLayerManager}
     */
    AoTVectorLayerManager.prototype.removeLayer = function(id) {
        var layerInfo = this.layers.get(id);
        if (!layerInfo) {
            console.warn('[AoTVectorLayerManager] Layer not found:', id);
            return this;
        }

        // Unregister from interactive events
        this._unregisterInteractiveLayer(id);

        try {
            this.map.removeLayer(id);
            
            // Remove from source's layer list
            var source = this.sources.get(layerInfo.sourceId);
            if (source) {
                var idx = source.layers.indexOf(id);
                if (idx > -1) {
                    source.layers.splice(idx, 1);
                }
            }
            
            this.layers.delete(id);
            console.log('[AoTVectorLayerManager] Layer removed:', id);
        } catch (e) {
            console.error('[AoTVectorLayerManager] Failed to remove layer:', id, e);
        }

        return this;
    };

    /**
     * Get layer information
     * @param {string} id - Layer ID
     * @returns {Object|null}
     */
    AoTVectorLayerManager.prototype.getLayer = function(id) {
        return this.layers.get(id) || null;
    };

    /**
     * Check if layer exists
     * @param {string} id - Layer ID
     * @returns {boolean}
     */
    AoTVectorLayerManager.prototype.hasLayer = function(id) {
        return this.layers.has(id);
    };

    /**
     * Get all layers
     * @returns {Array}
     */
    AoTVectorLayerManager.prototype.getAllLayers = function() {
        return Array.from(this.layers.keys());
    };

    // ========================================
    // Style Management
    // ========================================

    /**
     * Set or update layer style
     * @param {string} layerId - Layer ID
     * @param {Object} style - Style properties (paint, layout)
     * @param {Object} [style.paint] - Paint properties
     * @param {Object} [style.layout] - Layout properties
     * @returns {AoTVectorLayerManager}
     */
    AoTVectorLayerManager.prototype.setLayerStyle = function(layerId, style) {
        if (!this.layers.has(layerId)) {
            console.warn('[AoTVectorLayerManager] Layer not found:', layerId);
            return this;
        }

        try {
            // Update paint properties
            if (style.paint) {
                for (var prop in style.paint) {
                    this.map.setPaintProperty(layerId, prop, style.paint[prop]);
                }
            }

            // Update layout properties
            if (style.layout) {
                for (var layoutProp in style.layout) {
                    this.map.setLayoutProperty(layerId, layoutProp, style.layout[layoutProp]);
                }
            }

            console.log('[AoTVectorLayerManager] Layer style updated:', layerId);
        } catch (e) {
            console.error('[AoTVectorLayerManager] Failed to update layer style:', layerId, e);
        }

        return this;
    };

    /**
     * Get current layer style
     * @param {string} layerId - Layer ID
     * @returns {Object|null}
     */
    AoTVectorLayerManager.prototype.getLayerStyle = function(layerId) {
        if (!this.layers.has(layerId)) {
            return null;
        }

        var layer = this.map.getLayer(layerId);
        if (!layer) return null;

        return {
            paint: layer.paint || {},
            layout: layer.layout || {}
        };
    };

    /**
     * Set layer visibility
     * @param {string} layerId - Layer ID
     * @param {boolean} visible - Visibility state
     * @returns {AoTVectorLayerManager}
     */
    AoTVectorLayerManager.prototype.setLayerVisibility = function(layerId, visible) {
        if (!this.layers.has(layerId)) {
            console.warn('[AoTVectorLayerManager] Layer not found:', layerId);
            return this;
        }

        try {
            this.map.setLayoutProperty(
                layerId,
                'visibility',
                visible ? 'visible' : 'none'
            );
            console.log('[AoTVectorLayerManager] Layer visibility set:', layerId, visible);
        } catch (e) {
            console.error('[AoTVectorLayerManager] Failed to set visibility:', layerId, e);
        }

        return this;
    };

    /**
     * Set layer opacity
     * @param {string} layerId - Layer ID
     * @param {number} opacity - Opacity value (0-1)
     * @returns {AoTVectorLayerManager}
     */
    AoTVectorLayerManager.prototype.setLayerOpacity = function(layerId, opacity) {
        if (!this.layers.has(layerId)) {
            console.warn('[AoTVectorLayerManager] Layer not found:', layerId);
            return this;
        }

        var layer = this.map.getLayer(layerId);
        if (!layer) return this;

        opacity = Math.max(0, Math.min(1, opacity));

        try {
            var paintProp;
            switch (layer.type) {
                case 'fill':
                    paintProp = 'fill-opacity';
                    break;
                case 'line':
                    paintProp = 'line-opacity';
                    break;
                case 'symbol':
                    paintProp = 'text-opacity';
                    break;
                case 'circle':
                    paintProp = 'circle-opacity';
                    break;
                case 'raster':
                    paintProp = 'raster-opacity';
                    break;
                default:
                    paintProp = 'opacity';
            }

            this.map.setPaintProperty(layerId, paintProp, opacity);
        } catch (e) {
            console.error('[AoTVectorLayerManager] Failed to set opacity:', layerId, e);
        }

        return this;
    };

    // ========================================
    // Filter Management
    // ========================================

    /**
     * Set layer filter
     * @param {string} layerId - Layer ID
     * @param {Array} filter - MapLibre filter expression
     * @returns {AoTVectorLayerManager}
     */
    AoTVectorLayerManager.prototype.setFilter = function(layerId, filter) {
        if (!this.layers.has(layerId)) {
            console.warn('[AoTVectorLayerManager] Layer not found:', layerId);
            return this;
        }

        try {
            this.map.setFilter(layerId, filter);
            console.log('[AoTVectorLayerManager] Filter set on layer:', layerId);
        } catch (e) {
            console.error('[AoTVectorLayerManager] Failed to set filter:', layerId, e);
        }

        return this;
    };

    /**
     * Clear layer filter
     * @param {string} layerId - Layer ID
     * @returns {AoTVectorLayerManager}
     */
    AoTVectorLayerManager.prototype.clearFilter = function(layerId) {
        return this.setFilter(layerId, null);
    };

    /**
     * Get current layer filter
     * @param {string} layerId - Layer ID
     * @returns {Array|null}
     */
    AoTVectorLayerManager.prototype.getFilter = function(layerId) {
        if (!this.layers.has(layerId)) {
            return null;
        }

        try {
            return this.map.getFilter(layerId);
        } catch (e) {
            return null;
        }
    };

    // ========================================
    // Event Handling
    // ========================================

    /**
     * Register layer for click/hover events
     * @private
     */
    AoTVectorLayerManager.prototype._registerInteractiveLayer = function(layerId) {
        if (this._interactiveLayers.has(layerId)) return;
        
        this._interactiveLayers.add(layerId);
        
        if (this._interactiveLayers.size === 1) {
            this.map.on('click', this._onClick);
            this.map.on('mouseenter', this._onMouseEnter);
            this.map.on('mouseleave', this._onMouseLeave);
        }
    };

    /**
     * Unregister layer from click/hover events
     * @private
     */
    AoTVectorLayerManager.prototype._unregisterInteractiveLayer = function(layerId) {
        this._interactiveLayers.delete(layerId);
        
        if (this._interactiveLayers.size === 0) {
            this.map.off('click', this._onClick);
            this.map.off('mouseenter', this._onMouseEnter);
            this.map.off('mouseleave', this._onMouseLeave);
        }
    };

    /**
     * Handle click event on layers
     * @private
     */
    AoTVectorLayerManager.prototype._onClick = function(e) {
        var self = this;
        var features = self.map.queryRenderedFeatures(e.point, {
            layers: Array.from(self._interactiveLayers)
        });

        if (features.length > 0) {
            var feature = features[0];
            var layerId = feature.layer.id;
            
            // Notify registered click handlers
            var handlers = self.eventHandlers.get('click') || [];
            handlers.forEach(function(handler) {
                handler.call(self, feature, e.lngLat, layerId);
            });

            // Emit custom event
            self.map.fire('aot:layerclick', {
                feature: feature,
                lngLat: e.lngLat,
                layerId: layerId,
                point: e.point
            });
        }
    };

    /**
     * Handle mouse enter on layers
     * @private
     */
    AoTVectorLayerManager.prototype._onMouseEnter = function(e) {
        if (this.options.cursorOnHover) {
            var features = this.map.queryRenderedFeatures(e.point, {
                layers: Array.from(this._interactiveLayers)
            });

            if (features.length > 0) {
                this.map.getCanvas().style.cursor = 'pointer';
            }
        }
    };

    /**
     * Handle mouse leave on layers
     * @private
     */
    AoTVectorLayerManager.prototype._onMouseLeave = function() {
        if (this.options.cursorOnHover) {
            this.map.getCanvas().style.cursor = '';
        }
    };

    /**
     * Register click event handler for layers
     * @param {Function} callback - Callback function (feature, lngLat, layerId)
     * @returns {Function} Unsubscribe function
     */
    AoTVectorLayerManager.prototype.onLayerClick = function(callback) {
        if (typeof callback !== 'function') {
            console.error('[AoTVectorLayerManager] Callback must be a function');
            return function() {};
        }

        var handlers = this.eventHandlers.get('click') || [];
        handlers.push(callback);
        this.eventHandlers.set('click', handlers);

        // Return unsubscribe function
        var self = this;
        return function() {
            var idx = handlers.indexOf(callback);
            if (idx > -1) {
                handlers.splice(idx, 1);
            }
        };
    };

    /**
     * Register hover event handler for layers
     * @param {Function} callback - Callback function (feature, lngLat, layerId, type)
     * @returns {Function} Unsubscribe function
     */
    AoTVectorLayerManager.prototype.onLayerHover = function(callback) {
        if (typeof callback !== 'function') {
            console.error('[AoTVectorLayerManager] Callback must be a function');
            return function() {};
        }

        var handlers = this.eventHandlers.get('hover') || [];
        handlers.push(callback);
        this.eventHandlers.set('hover', handlers);

        var self = this;
        return function() {
            var idx = handlers.indexOf(callback);
            if (idx > -1) {
                handlers.splice(idx, 1);
            }
        };
    };

    // ========================================
    // Convenience Methods
    // ========================================

    /**
     * Add a styled polygon layer (fill + outline)
     * @param {string} layerId - Layer ID
     * @param {string} sourceId - Source ID
     * @param {Object} [style={}] - Style options
     * @param {string} [style.fillColor='#888888'] - Fill color
     * @param {number} [style.fillOpacity=0.3] - Fill opacity
     * @param {string} [style.strokeColor='#333333'] - Stroke color
     * @param {number} [style.strokeWidth=2] - Stroke width
     * @returns {AoTVectorLayerManager}
     */
    AoTVectorLayerManager.prototype.addPolygonLayer = function(layerId, sourceId, style) {
        style = style || {};
        
        // Add fill layer
        this.addLayer({
            id: layerId,
            sourceId: sourceId,
            type: 'fill',
            paint: {
                'fill-color': style.fillColor || '#888888',
                'fill-opacity': style.fillOpacity !== undefined ? style.fillOpacity : 0.3
            },
            interactive: style.interactive
        });

        // Add outline layer
        this.addLayer({
            id: layerId + '-outline',
            sourceId: sourceId,
            type: 'line',
            paint: {
                'line-color': style.strokeColor || '#333333',
                'line-width': style.strokeWidth || 2
            },
            interactive: false
        });

        return this;
    };

    /**
     * Add a line layer
     * @param {string} layerId - Layer ID
     * @param {string} sourceId - Source ID
     * @param {Object} [style={}] - Style options
     * @param {string} [style.color='#007bff'] - Line color
     * @param {number} [style.width=3] - Line width
     * @param {Array} [style.dashArray] - Dash array
     * @returns {AoTVectorLayerManager}
     */
    AoTVectorLayerManager.prototype.addLineLayer = function(layerId, sourceId, style) {
        style = style || {};
        
        var paint = {
            'line-color': style.color || '#007bff',
            'line-width': style.width || 3,
            'line-opacity': style.opacity !== undefined ? style.opacity : 0.9
        };

        if (style.dashArray) {
            paint['line-dasharray'] = style.dashArray;
        }

        this.addLayer({
            id: layerId,
            sourceId: sourceId,
            type: 'line',
            paint: paint,
            interactive: style.interactive
        });

        return this;
    };

    /**
     * Add a circle/point layer
     * @param {string} layerId - Layer ID
     * @param {string} sourceId - Source ID
     * @param {Object} [style={}] - Style options
     * @param {string} [style.color='#007bff'] - Circle color
     * @param {number} [style.radius=6] - Circle radius
     * @returns {AoTVectorLayerManager}
     */
    AoTVectorLayerManager.prototype.addCircleLayer = function(layerId, sourceId, style) {
        style = style || {};
        
        this.addLayer({
            id: layerId,
            sourceId: sourceId,
            type: 'circle',
            paint: {
                'circle-radius': style.radius || 6,
                'circle-color': style.color || '#007bff',
                'circle-opacity': style.opacity !== undefined ? style.opacity : 0.9,
                'circle-stroke-width': 2,
                'circle-stroke-color': '#ffffff'
            },
            interactive: style.interactive
        });

        return this;
    };

    /**
     * Add a symbol/label layer
     * @param {string} layerId - Layer ID
     * @param {string} sourceId - Source ID
     * @param {Object} [style={}] - Style options
     * @param {string} [style.textField='name'] - Text field property
     * @param {string} [style.color='#333333'] - Text color
     * @returns {AoTVectorLayerManager}
     */
    AoTVectorLayerManager.prototype.addSymbolLayer = function(layerId, sourceId, style) {
        style = style || {};
        
        this.addLayer({
            id: layerId,
            sourceId: sourceId,
            type: 'symbol',
            layout: {
                'text-field': ['get', style.textField || 'name'],
                'text-font': ['Noto Sans Regular'],
                'text-size': style.size || 12,
                'text-offset': style.offset || [0, 1],
                'text-anchor': 'top'
            },
            paint: {
                'text-color': style.color || '#333333',
                'text-halo-color': '#ffffff',
                'text-halo-width': 2
            },
            interactive: false
        });

        return this;
    };

    // ========================================
    // MapTiler Vector Tile Helpers
    // ========================================

    /**
     * Add MapTiler vector source
     * @param {string} [apiKey] - MapTiler API key
     * @param {string} [style='streets'] - Style name
     * @returns {AoTVectorLayerManager}
     */
    AoTVectorLayerManager.prototype.addMapTilerSource = function(apiKey, style) {
        style = style || 'streets';
        
        var styleUrls = {
            streets: 'https://api.maptiler.com/tiles/v3-free/style.json',
            outdoor: 'https://api.maptiler.com/tiles/outdoor-v3-free/style.json',
            light: 'https://api.maptiler.com/tiles/light-v3-free/style.json',
            dark: 'https://api.maptiler.com/tiles/dark-v3-free/style.json',
            satellite: 'https://api.maptiler.com/tiles/satellite-v2/style.json'
        };

        var styleUrl = styleUrls[style] || styleUrls.streets;
        if (apiKey) {
            styleUrl += (styleUrl.indexOf('?') > -1 ? '&' : '?') + 'key=' + apiKey;
        }

        // Note: MapTiler free styles don't require API key for basic usage
        // but paid tiles do. For full implementation, use addVectorSource with
        // proper tile URLs
        
        console.log('[AoTVectorLayerManager] MapTiler source configured:', style);
        return this;
    };

    /**
     * Add OSM vector source
     * @param {string} id - Source ID
     * @returns {AoTVectorLayerManager}
     */
    AoTVectorLayerManager.prototype.addOSMVectorSource = function(id) {
        id = id || 'osm-vector';
        
        var tiles = [
            'https://tile.openstreetmap.fr/hot/{z}/{x}/{y}.pbf'
        ];

        this.addVectorSource(id, {
            tiles: tiles,
            minzoom: 0,
            maxzoom: 18,
            attribution: '© OpenStreetMap contributors'
        });

        return this;
    };

    // ========================================
    // Utility Methods
    // ========================================

    /**
     * Get map features at a point
     * @param {Array} layerIds - Array of layer IDs to query
     * @param {Array} point - [x, y] pixel coordinates
     * @returns {Array} Array of features
     */
    AoTVectorLayerManager.prototype.getFeaturesAtPoint = function(layerIds, point) {
        return this.map.queryRenderedFeatures(point, {
            layers: layerIds
        });
    };

    /**
     * Get features within a bounding box
     * @param {Array} bounds - [[west, south], [east, north]]
     * @param {Array} [layerIds] - Array of layer IDs to query
     * @returns {Array} Array of features
     */
    AoTVectorLayerManager.prototype.getFeaturesInBounds = function(bounds, layerIds) {
        var options = {};
        if (layerIds && layerIds.length > 0) {
            options.layers = layerIds;
        }

        return this.map.queryRenderedFeatures(bounds, options);
    };

    /**
     * Fit map to layer extent
     * @param {string} sourceId - Source ID
     * @param {number} [padding=50] - Padding in pixels
     * @returns {AoTVectorLayerManager}
     */
    AoTVectorLayerManager.prototype.fitToSource = function(sourceId, padding) {
        padding = padding || 50;
        
        var source = this.sources.get(sourceId);
        if (!source) {
            console.warn('[AoTVectorLayerManager] Source not found:', sourceId);
            return this;
        }

        try {
            var features = this.map.querySourceFeatures(sourceId);
            if (features.length > 0) {
                var bbox = this._getBoundingBox(features);
                if (bbox) {
                    this.map.fitBounds(bbox, {
                        padding: padding,
                        maxZoom: 16
                    });
                }
            }
        } catch (e) {
            console.error('[AoTVectorLayerManager] Failed to fit bounds:', e);
        }

        return this;
    };

    /**
     * Calculate bounding box from features
     * @private
     */
    AoTVectorLayerManager.prototype._getBoundingBox = function(features) {
        var minLng = Infinity, minLat = Infinity;
        var maxLng = -Infinity, maxLat = -Infinity;

        features.forEach(function(feature) {
            var geom = feature.geometry;
            if (!geom) return;

            this._updateBoundsFromGeometry(geom, function(lng, lat) {
                minLng = Math.min(minLng, lng);
                minLat = Math.min(minLat, lat);
                maxLng = Math.max(maxLng, lng);
                maxLat = Math.max(maxLat, lat);
            });
        }, this);

        if (minLng === Infinity) return null;

        return [[minLng, minLat], [maxLng, maxLat]];
    };

    /**
     * Update bounds from geometry
     * @private
     */
    AoTVectorLayerManager.prototype._updateBoundsFromGeometry = function(geom, callback) {
        var coords;

        switch (geom.type) {
            case 'Point':
                coords = geom.coordinates;
                callback(coords[0], coords[1]);
                break;
            case 'LineString':
            case 'MultiPoint':
                coords = geom.coordinates;
                coords.forEach(function(c) { callback(c[0], c[1]); });
                break;
            case 'Polygon':
            case 'MultiLineString':
                coords = geom.coordinates;
                coords.forEach(function(ring) {
                    ring.forEach(function(c) { callback(c[0], c[1]); });
                });
                break;
            case 'MultiPolygon':
                coords = geom.coordinates;
                coords.forEach(function(poly) {
                    poly.forEach(function(ring) {
                        ring.forEach(function(c) { callback(c[0], c[1]); });
                    });
                });
                break;
        }
    };

    /**
     * Destroy the manager and clean up
     */
    AoTVectorLayerManager.prototype.destroy = function() {
        var self = this;

        // Remove all event handlers
        this.map.off('click', this._onClick);
        this.map.off('mouseenter', this._onMouseEnter);
        this.map.off('mouseleave', this._onMouseLeave);

        // Remove all layers
        this.layers.forEach(function(info, layerId) {
            try {
                self.map.removeLayer(layerId);
            } catch (e) {
                console.warn('[AoTVectorLayerManager] Failed to remove layer:', layerId);
            }
        });

        // Remove all sources
        this.sources.forEach(function(info, sourceId) {
            try {
                self.map.removeSource(sourceId);
            } catch (e) {
                console.warn('[AoTVectorLayerManager] Failed to remove source:', sourceId);
            }
        });

        // Clear registries
        this.layers.clear();
        this.sources.clear();
        this.eventHandlers.clear();
        this._interactiveLayers.clear();

        this.map = null;
        console.log('[AoTVectorLayerManager] Manager destroyed');
    };

    // Export to global namespace
    window.AoTVectorLayerManager = AoTVectorLayerManager;

})(window);
