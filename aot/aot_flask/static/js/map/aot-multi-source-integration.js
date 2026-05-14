/**
 * aot-multi-source-integration.js
 * Integration helper for AoTMultiSourceManager with existing AoT map system
 * 
 * @version 1.0.0
 * @requires aot-multi-source-manager.js
 */

(function(window) {
    'use strict';

    /**
     * AoT Multi-Source Integration Helper
     * Bridges AoTMultiSourceManager with AoTMapLoader
     */
    var AoTMultiSourceIntegration = {

        // Manager instances per map container
        _instances: {},

        /**
         * Initialize multi-source support for a map
         * @param {string|L.Map} mapOrContainerId - Leaflet map or container ID
         * @param {Object} options - Integration options
         * @returns {AoTMultiSourceManager} Manager instance
         */
        init: function(mapOrContainerId, options) {
            var self = this;
            options = options || {};

            var map;
            var containerId;

            if (typeof mapOrContainerId === 'string') {
                containerId = mapOrContainerId;
                // Find map by container ID
                if (window.AoTMapApp && window.AoTMapApp[containerId]) {
                    map = window.AoTMapApp[containerId].map;
                }
            } else if (mapOrContainerId && mapOrContainerId.on) {
                map = mapOrContainerId;
                containerId = map._container ? map._container.id : 'unknown';
            }

            if (!map) {
                console.error('[AoTMultiSourceIntegration] Map not found');
                return null;
            }

            // Initialize manager
            var manager = Object.create(window.AoTMultiSourceManager);
            manager.init(map);

            // Load API keys from config if available
            if (window.AOT_GEO_CONFIG && window.AOT_GEO_CONFIG.keys) {
                var keys = window.AOT_GEO_CONFIG.keys;
                
                // VWorld
                if (keys.vworld) {
                    manager.setApiKey('vworld_base', keys.vworld);
                    manager.setApiKey('vworld_satellite', keys.vworld);
                }
                
                // MapTiler
                if (keys.maptiler) {
                    manager.setApiKey('maptiler_vector', keys.maptiler);
                    manager.setApiKey('maptiler_satellite', keys.maptiler);
                }
                
                // Google
                if (keys.google) {
                    manager.setApiKey('google_street', keys.google);
                    manager.setApiKey('google_satellite', keys.google);
                    manager.setApiKey('google_hybrid', keys.google);
                }
            }

            // Register custom sources from config
            if (window.AOT_GEO_CONFIG && window.AOT_GEO_CONFIG.customMapSources) {
                window.AOT_GEO_CONFIG.customMapSources.forEach(function(source) {
                    manager.registerSource(source);
                });
            }

            // Add switcher control if requested
            if (options.addControl !== false) {
                var control = manager.createSwitcherControl({
                    position: options.controlPosition || 'topright'
                });
                control.addTo(map);
            }

            // Set default source
            var defaultSourceId = options.defaultSource || 'osm_standard';
            if (options.activateDefault !== false) {
                manager.switchSource(defaultSourceId, { animate: false });
            }

            // Store instance
            this._instances[containerId] = manager;

            // Cleanup on map remove
            map.on('unload', function() {
                self.destroy(containerId);
            });

            console.log('[AoTMultiSourceIntegration] Initialized for:', containerId);
            return manager;
        },

        /**
         * Get manager instance for a container
         * @param {string} containerId - Container ID
         * @returns {AoTMultiSourceManager|null} Manager instance
         */
        getManager: function(containerId) {
            return this._instances[containerId] || null;
        },

        /**
         * Destroy instance for a container
         * @param {string} containerId - Container ID
         */
        destroy: function(containerId) {
            if (this._instances[containerId]) {
                this._instances[containerId].destroy();
                delete this._instances[containerId];
                console.log('[AoTMultiSourceIntegration] Destroyed for:', containerId);
            }
        },

        /**
         * Create a basemap switcher UI button
         * @param {string} containerId - Container ID
         * @param {HTMLElement} targetElement - Element to attach button
         * @param {Object} options - Button options
         * @returns {HTMLElement} Button element
         */
        createSwitcherButton: function(containerId, targetElement, options) {
            var manager = this.getManager(containerId);
            if (!manager || !targetElement) return null;

            options = options || {};

            var button = document.createElement('button');
            button.className = 'aot-basemap-switcher-btn';
            button.innerHTML = options.icon || '🗺️';
            button.title = options.title || '베이스맵 전환';
            button.style.cssText = options.style || 'padding: 8px; border: none; background: white; border-radius: 4px; cursor: pointer; box-shadow: 0 2px 6px rgba(0,0,0,0.3);';

            // Create dropdown on click
            var dropdown = null;
            
            button.onclick = function(e) {
                e.stopPropagation();

                // Close existing dropdown
                if (dropdown) {
                    document.body.removeChild(dropdown);
                    dropdown = null;
                    return;
                }

                // Create dropdown
                dropdown = document.createElement('div');
                dropdown.className = 'aot-basemap-dropdown';
                dropdown.style.cssText = 'position: absolute; background: white; border-radius: 4px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); padding: 8px; z-index: 10000; min-width: 180px;';

                // Get button position
                var rect = button.getBoundingClientRect();
                dropdown.style.left = rect.left + 'px';
                dropdown.style.top = (rect.bottom + 4) + 'px';

                // Get active source
                var activeId = manager.getActiveSourceId();

                // Add source options
                var sources = manager.getAllSources();
                Object.keys(sources).forEach(function(sourceId) {
                    var source = sources[sourceId];
                    
                    var item = document.createElement('div');
                    item.style.cssText = 'padding: 8px 12px; cursor: pointer; border-radius: 3px; margin: 2px 0; font-size: 13px;';
                    
                    // Icon
                    var icon = source.type === 'vector' ? '●' : '■';
                    var iconColor = source.type === 'vector' ? '#2196F3' : '#4CAF50';
                    
                    item.innerHTML = '<span style="color:' + iconColor + '; margin-right: 8px;">' + icon + '</span>' + source.name;
                    
                    if (sourceId === activeId) {
                        item.style.background = '#e3f2fd';
                        item.style.fontWeight = 'bold';
                    }

                    item.onmouseover = function() {
                        if (sourceId !== activeId) {
                            item.style.background = '#f5f5f5';
                        }
                    };
                    item.onmouseout = function() {
                        if (sourceId !== activeId) {
                            item.style.background = 'transparent';
                        }
                    };
                    item.onclick = function() {
                        manager.switchSource(sourceId, { animate: true });
                        document.body.removeChild(dropdown);
                        dropdown = null;
                    };

                    dropdown.appendChild(item);
                });

                document.body.appendChild(dropdown);

                // Close on outside click
                var closeHandler = function(e) {
                    if (!dropdown.contains(e.target) && e.target !== button) {
                        document.body.removeChild(dropdown);
                        dropdown = null;
                        document.removeEventListener('click', closeHandler);
                    }
                };
                setTimeout(function() {
                    document.addEventListener('click', closeHandler);
                }, 0);
            };

            return button;
        },

        /**
         * Add a custom source from layer config
         * @param {string} containerId - Container ID
         * @param {Object} layerConfig - Layer configuration (matches AoT layer format)
         * @returns {string|null} Source ID or null
         */
        addSourceFromLayer: function(containerId, layerConfig) {
            var manager = this.getManager(containerId);
            if (!manager) {
                console.warn('[AoTMultiSourceIntegration] Manager not found for:', containerId);
                return null;
            }

            var sourceId = layerConfig.id || ('custom_' + Date.now());

            var sourceConfig = {
                id: sourceId,
                name: layerConfig.name || sourceId,
                provider: this._detectProvider(layerConfig.url),
                type: layerConfig.type === 'vector' ? 'vector' : 'raster',
                url: layerConfig.url,
                options: Object.assign({}, layerConfig.options || {}, {
                    api_key: layerConfig.api_key
                }),
                attribution: layerConfig.attribution || '',
                isVector: layerConfig.type === 'vector',
                metadata: {
                    originalConfig: layerConfig
                }
            };

            manager.registerSource(sourceConfig);
            return sourceId;
        },

        /**
         * Detect provider from URL
         * @private
         */
        _detectProvider: function(url) {
            if (!url) return 'unknown';

            url = url.toLowerCase();

            if (url.indexOf('vworld') !== -1) return 'vworld';
            if (url.indexOf('maptiler') !== -1) return 'maptiler';
            if (url.indexOf('openstreetmap') !== -1) return 'osm';
            if (url.indexOf('google') !== -1 || url.indexOf('mt1.google') !== -1) return 'google';
            if (url.indexOf('arcgis') !== -1 || url.indexOf('esri') !== -1) return 'esri';
            if (url.indexOf('bing') !== -1) return 'bing';

            return 'custom';
        }
    };

    // Export to global namespace
    window.AoTMultiSourceIntegration = AoTMultiSourceIntegration;

    /**
     * Auto-initialize on map ready
     * Hooks into AoTMapLoader initialization
     */
    $(document).ready(function() {
        // Hook into AoT map initialization
        if (window.AoTMapLoader) {
            var originalInit = window.AoTMapLoader.initMap;
            
            window.AoTMapLoader.initMap = function(containerId, mapType, customOptions) {
                var result = originalInit.apply(this, arguments);

                if (result && result.map) {
                    // Auto-initialize multi-source if enabled in config
                    if (window.AOT_GEO_CONFIG && window.AOT_GEO_CONFIG.enableMultiSource !== false) {
                        // Delay to ensure DOM is ready
                        setTimeout(function() {
                            AoTMultiSourceIntegration.init(result.map, {
                                addControl: false, // We'll add our own control
                                defaultSource: window.AOT_GEO_CONFIG.defaultMapSource || 'osm_standard'
                            });
                        }, 100);
                    }
                }

                return result;
            };
        }
    });

})(window);
