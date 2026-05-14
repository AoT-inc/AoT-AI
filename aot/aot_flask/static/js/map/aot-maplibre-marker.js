/**
 * aot-maplibre-marker.js
 * Marker and Popup Manager for AoT Map System
 * Manages markers, popups, and marker groups with MapLibre-GL
 * 
 * @version 1.0.0
 * @requires maplibre-gl (loaded from CDN or bundled)
 * @namespace AoTMarkerManager
 */

(function(window) {
    'use strict';

    /**
     * AoTMarkerManager
     * Manages markers, popups, and groups for MapLibre-GL
     * 
     * @param {Object} map - MapLibre-GL map instance
     * @param {Object} options - Configuration options
     */
    var AoTMarkerManager = function(map, options) {
        this.map = map;
        this.options = Object.assign({}, this._getDefaultOptions(), options);
        
        // Registry for markers
        this.markers = new Map();
        this.markerIdCounter = 0;
        
        // Registry for popups
        this.popups = new Map();
        this.popupIdCounter = 0;
        
        // Registry for marker groups
        this.groups = new Map();
        
        // Event handlers
        this.eventHandlers = {
            click: [],
            hover: [],
            dragend: []
        };
        
        // Bind methods
        this._onMarkerClick = this._onMarkerClick.bind(this);
        this._onMarkerMouseEnter = this._onMarkerMouseEnter.bind(this);
        this._onMarkerMouseLeave = this._onMarkerMouseLeave.bind(this);
    };

    /**
     * Default configuration options
     * @private
     */
    AoTMarkerManager.prototype._getDefaultOptions = function() {
        return {
            defaultMarkerColor: '#3FB1CE',
            defaultPopupOffset: 25,
            cursorOnHover: true,
            autoPan: true,
            closeButton: true,
            closeOnClick: true,
            maxWidth: 300,
            // AoT-specific defaults
            markerTypeDefaults: {
                site: {
                    color: '#DF5353',
                    scale: 1.2,
                    icon: 'marker-site'
                },
                zone: {
                    color: '#28a745',
                    scale: 1.0,
                    icon: 'marker-zone'
                },
                facility: {
                    color: '#82898f',
                    scale: 0.9,
                    icon: 'marker-facility'
                },
                device: {
                    color: '#007bff',
                    scale: 0.8,
                    icon: 'marker-device'
                },
                equipment: {
                    color: '#ffc107',
                    scale: 0.85,
                    icon: 'marker-equipment'
                }
            }
        };
    };

    // ========================================
    // Marker Management
    // ========================================

    /**
     * Add a marker to the map
     * @param {Object} config - Marker configuration
     * @param {Array|Object} config.lngLat - [lng, lat] or {lng, lat}
     * @param {HTMLElement} [config.element] - Custom HTML element
     * @param {string} [config.id] - Custom marker ID
     * @param {string} [config.type] - Marker type (site, zone, facility, device, equipment)
     * @param {string} [config.color] - Marker color
     * @param {number} [config.scale] - Marker scale
     * @param {string} [config.html] - Custom HTML for marker
     * @param {boolean} [config.draggable] - Enable drag functionality
     * @param {Object} [config.properties] - Custom properties for events
     * @param {string} [config.groupId] - Group ID to add marker to
     * @returns {string} Marker ID
     */
    AoTMarkerManager.prototype.addMarker = function(config) {
        var self = this;
        
        // Generate marker ID
        var markerId = config.id || ('marker_' + (++this.markerIdCounter));
        
        // Check if marker already exists
        if (this.markers.has(markerId)) {
            console.warn('[AoTMarkerManager] Marker already exists:', markerId);
            return markerId;
        }
        
        // Parse coordinates
        var lngLat;
        if (Array.isArray(config.lngLat)) {
            lngLat = { lng: config.lngLat[0], lat: config.lngLat[1] };
        } else if (typeof config.lngLat === 'object') {
            lngLat = config.lngLat;
        } else {
            console.error('[AoTMarkerManager] Invalid coordinates provided');
            return null;
        }
        
        // Create marker element
        var element;
        if (config.element) {
            element = config.element;
        } else if (config.html) {
            element = document.createElement('div');
            element.innerHTML = config.html;
        } else {
            element = this._createDefaultMarker(config);
        }
        
        // Apply custom classes
        if (config.className) {
            config.className.split(' ').forEach(function(cls) {
                element.classList.add(cls);
            });
        }
        
        // Create marker options
        var markerOptions = {
            element: element,
            anchor: config.anchor || 'center',
            offset: config.offset || [0, 0],
            draggable: config.draggable || false
        };
        
        // Apply type-specific styling
        if (config.type && !config.element && !config.html) {
            var typeDefaults = this.options.markerTypeDefaults[config.type];
            if (typeDefaults) {
                markerOptions.color = config.color || typeDefaults.color;
                markerOptions.scale = config.scale || typeDefaults.scale;
            }
        } else if (config.color) {
            markerOptions.color = config.color;
        }
        
        // Create MapLibre Marker
        var marker = new maplibregl.Marker(markerOptions)
            .setLngLat([lngLat.lng, lngLat.lat])
            .addTo(this.map);
        
        // Attach event listeners
        if (!config.draggable) {
            element.addEventListener('click', function(e) {
                self._onMarkerClick(markerId, e);
            });
        }
        
        if (this.options.cursorOnHover) {
            element.addEventListener('mouseenter', function() {
                self._onMarkerMouseEnter(markerId);
            });
            element.addEventListener('mouseleave', function() {
                self._onMarkerMouseLeave(markerId);
            });
        }
        
        // Handle drag events
        if (config.draggable) {
            marker.on('dragend', function() {
                self._onMarkerDragEnd(markerId, marker);
            });
        }
        
        // Store marker data
        this.markers.set(markerId, {
            marker: marker,
            element: element,
            lngLat: lngLat,
            type: config.type || 'default',
            properties: config.properties || {},
            groupId: config.groupId || null,
            visible: true,
            popup: null
        });
        
        // Add to group if specified
        if (config.groupId) {
            this._addMarkerToGroup(markerId, config.groupId);
        }
        
        console.log('[AoTMarkerManager] Marker added:', markerId);
        return markerId;
    };

    /**
     * Create default marker element
     * @private
     */
    AoTMarkerManager.prototype._createDefaultMarker = function(config) {
        var color = config.color || this.options.defaultMarkerColor;
        var scale = config.scale || 1;
        
        var element = document.createElement('div');
        element.className = 'aot-marker';
        
        // Create SVG marker
        var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('width', (27 * scale) + 'px');
        svg.setAttribute('height', (41 * scale) + 'px');
        svg.setAttribute('viewBox', '0 0 27 41');
        svg.style.display = 'block';
        
        // Background path
        var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', 'M27,13.5 C27,19.074644 20.250001,27.000002 14.75,34.500002 C14.016665,35.500004 12.983335,35.500004 12.25,34.500002 C6.7499993,27.000002 0,19.222562 0,13.5 C0,6.0441559 6.0441559,0 13.5,0 C20.955844,0 27,6.0441559 27,13.5 Z');
        path.setAttribute('fill', color);
        
        // Shadow
        var shadow = document.createElementNS('http://www.w3.org/2000/svg', 'ellipse');
        shadow.setAttribute('cx', '13.5');
        shadow.setAttribute('cy', '38.8');
        shadow.setAttribute('rx', '10.5');
        shadow.setAttribute('ry', '5.25');
        shadow.setAttribute('fill', 'rgba(0,0,0,0.2)');
        
        svg.appendChild(shadow);
        svg.appendChild(path);
        element.appendChild(svg);
        
        // Add type indicator if specified
        if (config.type) {
            element.setAttribute('data-type', config.type);
            element.classList.add('aot-marker-' + config.type);
        }
        
        return element;
    };

    /**
     * Remove a marker from the map
     * @param {string} markerId - Marker ID
     * @returns {AoTMarkerManager}
     */
    AoTMarkerManager.prototype.removeMarker = function(markerId) {
        var markerData = this.markers.get(markerId);
        if (!markerData) {
            console.warn('[AoTMarkerManager] Marker not found:', markerId);
            return this;
        }
        
        // Remove from group if in one
        if (markerData.groupId) {
            this._removeMarkerFromGroup(markerId, markerData.groupId);
        }
        
        // Remove associated popup
        if (markerData.popup) {
            this.removePopup(markerData.popup);
        }
        
        // Remove marker from map
        markerData.marker.remove();
        
        // Remove from registry
        this.markers.delete(markerId);
        
        console.log('[AoTMarkerManager] Marker removed:', markerId);
        return this;
    };

    /**
     * Get marker by ID
     * @param {string} markerId - Marker ID
     * @returns {Object|null} Marker data
     */
    AoTMarkerManager.prototype.getMarker = function(markerId) {
        return this.markers.get(markerId) || null;
    };

    /**
     * Update marker position
     * @param {string} markerId - Marker ID
     * @param {Array|Object} lngLat - New coordinates
     * @returns {AoTMarkerManager}
     */
    AoTMarkerManager.prototype.setMarkerPosition = function(markerId, lngLat) {
        var markerData = this.markers.get(markerId);
        if (!markerData) {
            console.warn('[AoTMarkerManager] Marker not found:', markerId);
            return this;
        }
        
        var coords;
        if (Array.isArray(lngLat)) {
            coords = lngLat;
        } else if (typeof lngLat === 'object') {
            coords = [lngLat.lng, lngLat.lat];
        }
        
        markerData.marker.setLngLat(coords);
        markerData.lngLat = { lng: coords[0], lat: coords[1] };
        
        return this;
    };

    /**
     * Show/hide a marker
     * @param {string} markerId - Marker ID
     * @param {boolean} visible - Visibility state
     * @returns {AoTMarkerManager}
     */
    AoTMarkerManager.prototype.setMarkerVisible = function(markerId, visible) {
        var markerData = this.markers.get(markerId);
        if (!markerData) {
            console.warn('[AoTMarkerManager] Marker not found:', markerId);
            return this;
        }
        
        markerData.visible = visible;
        markerData.element.style.display = visible ? 'block' : 'none';
        
        return this;
    };

    /**
     * Get all markers
     * @returns {Array} Array of marker IDs
     */
    AoTMarkerManager.prototype.getAllMarkers = function() {
        return Array.from(this.markers.keys());
    };

    // ========================================
    // Marker Group Management
    // ========================================

    /**
     * Create a marker group
     * @param {string} groupId - Group identifier
     * @param {Object} options - Group options
     * @param {string} [options.name] - Group name
     * @param {boolean} [options.visible=true] - Initial visibility
     * @param {string} [options.type] - Group type (site, zone, facility)
     * @returns {AoTMarkerManager}
     */
    AoTMarkerManager.prototype.addMarkerGroup = function(groupId, options) {
        options = options || {};
        
        if (this.groups.has(groupId)) {
            console.warn('[AoTMarkerManager] Group already exists:', groupId);
            return this;
        }
        
        this.groups.set(groupId, {
            id: groupId,
            name: options.name || groupId,
            type: options.type || 'default',
            markerIds: [],
            visible: options.visible !== false,
            properties: options.properties || {}
        });
        
        console.log('[AoTMarkerManager] Marker group created:', groupId);
        return this;
    };

    /**
     * Remove a marker group
     * @param {string} groupId - Group ID
     * @param {boolean} [removeMarkers=true] - Also remove markers in group
     * @returns {AoTMarkerManager}
     */
    AoTMarkerManager.prototype.removeMarkerGroup = function(groupId, removeMarkers) {
        var group = this.groups.get(groupId);
        if (!group) {
            console.warn('[AoTMarkerManager] Group not found:', groupId);
            return this;
        }
        
        // Remove markers if requested
        if (removeMarkers !== false) {
            group.markerIds.forEach(function(markerId) {
                this.removeMarker(markerId);
            }, this);
        } else {
            // Just remove from group
            group.markerIds.forEach(function(markerId) {
                var markerData = this.markers.get(markerId);
                if (markerData) {
                    markerData.groupId = null;
                }
            }, this);
        }
        
        this.groups.delete(groupId);
        console.log('[AoTMarkerManager] Marker group removed:', groupId);
        return this;
    };

    /**
     * Add marker to group
     * @private
     */
    AoTMarkerManager.prototype._addMarkerToGroup = function(markerId, groupId) {
        var group = this.groups.get(groupId);
        var markerData = this.markers.get(markerId);
        
        if (!group || !markerData) {
            console.warn('[AoTMarkerManager] Group or marker not found');
            return;
        }
        
        // Remove from previous group if any
        if (markerData.groupId && markerData.groupId !== groupId) {
            this._removeMarkerFromGroup(markerId, markerData.groupId);
        }
        
        group.markerIds.push(markerId);
        markerData.groupId = groupId;
    };

    /**
     * Remove marker from group
     * @private
     */
    AoTMarkerManager.prototype._removeMarkerFromGroup = function(markerId, groupId) {
        var group = this.groups.get(groupId);
        var markerData = this.markers.get(markerId);
        
        if (!group || !markerData) return;
        
        var idx = group.markerIds.indexOf(markerId);
        if (idx > -1) {
            group.markerIds.splice(idx, 1);
        }
        markerData.groupId = null;
    };

    /**
     * Show/hide group
     * @param {string} groupId - Group ID
     * @param {boolean} visible - Visibility state
     * @returns {AoTMarkerManager}
     */
    AoTMarkerManager.prototype.setGroupVisible = function(groupId, visible) {
        var group = this.groups.get(groupId);
        if (!group) {
            console.warn('[AoTMarkerManager] Group not found:', groupId);
            return this;
        }
        
        group.visible = visible;
        group.markerIds.forEach(function(markerId) {
            this.setMarkerVisible(markerId, visible);
        }, this);
        
        return this;
    };

    /**
     * Get group info
     * @param {string} groupId - Group ID
     * @returns {Object|null}
     */
    AoTMarkerManager.prototype.getGroup = function(groupId) {
        return this.groups.get(groupId) || null;
    };

    /**
     * Get all groups
     * @returns {Array} Array of group IDs
     */
    AoTMarkerManager.prototype.getAllGroups = function() {
        return Array.from(this.groups.keys());
    };

    // ========================================
    // Popup Management
    // ========================================

    /**
     * Add a popup to a marker
     * @param {string} markerId - Marker ID
     * @param {Object} config - Popup configuration
     * @param {string} [config.content] - HTML content
     * @param {HTMLElement} [config.element] - Custom content element
     * @param {Object} [config.options] - MapLibre Popup options
     * @returns {string|null} Popup ID
     */
    AoTMarkerManager.prototype.addPopup = function(markerId, config) {
        var markerData = this.markers.get(markerId);
        if (!markerData) {
            console.warn('[AoTMarkerManager] Marker not found:', markerId);
            return null;
        }
        
        var popupId = 'popup_' + (++this.popupIdCounter);
        
        // Parse options
        var popupOptions = Object.assign({}, {
            closeButton: this.options.closeButton,
            closeOnClick: this.options.closeOnClick,
            maxWidth: this.options.maxWidth,
            offset: this.options.defaultPopupOffset
        }, config.options || {});
        
        // Create popup content
        var content;
        if (config.element) {
            content = config.element;
        } else if (config.content) {
            content = config.content;
        } else {
            content = '<div class="aot-popup-content">No content</div>';
        }
        
        // Create MapLibre Popup
        var popup = new maplibregl.Popup(popupOptions)
            .setHTML(content);
        
        // Attach to marker
        markerData.marker.setPopup(popup);
        
        // Store popup data
        this.popups.set(popupId, {
            id: popupId,
            popup: popup,
            markerId: markerId,
            content: content
        });
        
        markerData.popup = popupId;
        
        console.log('[AoTMarkerManager] Popup added to marker:', markerId);
        return popupId;
    };

    /**
     * Remove popup from marker
     * @param {string} popupId - Popup ID
     * @returns {AoTMarkerManager}
     */
    AoTMarkerManager.prototype.removePopup = function(popupId) {
        var popupData = this.popups.get(popupId);
        if (!popupData) {
            console.warn('[AoTMarkerManager] Popup not found:', popupId);
            return this;
        }
        
        var markerData = this.markers.get(popupData.markerId);
        if (markerData) {
            markerData.marker.setPopup(null);
            markerData.popup = null;
        }
        
        this.popups.delete(popupId);
        console.log('[AoTMarkerManager] Popup removed:', popupId);
        return this;
    };

    /**
     * Open popup
     * @param {string} popupId - Popup ID
     * @returns {AoTMarkerManager}
     */
    AoTMarkerManager.prototype.openPopup = function(popupId) {
        var popupData = this.popups.get(popupId);
        if (!popupData) {
            console.warn('[AoTMarkerManager] Popup not found:', popupId);
            return this;
        }
        
        popupData.popup.addTo(this.map);
        return this;
    };

    /**
     * Close popup
     * @param {string} popupId - Popup ID
     * @returns {AoTMarkerManager}
     */
    AoTMarkerManager.prototype.closePopup = function(popupId) {
        var popupData = this.popups.get(popupId);
        if (!popupData) {
            console.warn('[AoTMarkerManager] Popup not found:', popupId);
            return this;
        }
        
        popupData.popup.remove();
        return this;
    };

    /**
     * Toggle popup
     * @param {string} popupId - Popup ID
     * @returns {AoTMarkerManager}
     */
    AoTMarkerManager.prototype.togglePopup = function(popupId) {
        var popupData = this.popups.get(popupId);
        if (!popupData) {
            console.warn('[AoTMarkerManager] Popup not found:', popupId);
            return this;
        }
        
        if (popupData.popup.isOpen()) {
            popupData.popup.remove();
        } else {
            popupData.popup.addTo(this.map);
        }
        return this;
    };

    // ========================================
    // Event Handling
    // ========================================

    /**
     * Handle marker click
     * @private
     */
    AoTMarkerManager.prototype._onMarkerClick = function(markerId, event) {
        var markerData = this.markers.get(markerId);
        if (!markerData) return;
        
        // Notify click handlers
        this.eventHandlers.click.forEach(function(handler) {
            handler.call(this, markerId, markerData, event);
        }, this);
        
        // Fire custom event
        this.map.fire('aot:markerclick', {
            markerId: markerId,
            lngLat: markerData.lngLat,
            properties: markerData.properties,
            type: markerData.type
        });
    };

    /**
     * Handle marker mouse enter
     * @private
     */
    AoTMarkerManager.prototype._onMarkerMouseEnter = function(markerId) {
        var markerData = this.markers.get(markerId);
        if (!markerData) return;
        
        // Change cursor
        if (this.options.cursorOnHover) {
            this.map.getCanvas().style.cursor = 'pointer';
        }
        
        // Notify hover handlers
        this.eventHandlers.hover.forEach(function(handler) {
            handler.call(this, markerId, markerData, 'enter');
        }, this);
        
        // Fire custom event
        this.map.fire('aot:markerhover', {
            markerId: markerId,
            lngLat: markerData.lngLat,
            properties: markerData.properties,
            type: 'enter'
        });
    };

    /**
     * Handle marker mouse leave
     * @private
     */
    AoTMarkerManager.prototype._onMarkerMouseLeave = function(markerId) {
        var markerData = this.markers.get(markerId);
        if (!markerData) return;
        
        // Reset cursor
        if (this.options.cursorOnHover) {
            this.map.getCanvas().style.cursor = '';
        }
        
        // Notify hover handlers
        this.eventHandlers.hover.forEach(function(handler) {
            handler.call(this, markerId, markerData, 'leave');
        }, this);
        
        // Fire custom event
        this.map.fire('aot:markerhover', {
            markerId: markerId,
            lngLat: markerData.lngLat,
            properties: markerData.properties,
            type: 'leave'
        });
    };

    /**
     * Handle marker drag end
     * @private
     */
    AoTMarkerManager.prototype._onMarkerDragEnd = function(markerId, marker) {
        var markerData = this.markers.get(markerId);
        if (!markerData) return;
        
        var newLngLat = marker.getLngLat();
        markerData.lngLat = { lng: newLngLat.lng, lat: newLngLat.lat };
        
        // Notify drag handlers
        this.eventHandlers.dragend.forEach(function(handler) {
            handler.call(this, markerId, markerData);
        }, this);
        
        // Fire custom event
        this.map.fire('aot:markerdragend', {
            markerId: markerId,
            lngLat: markerData.lngLat,
            properties: markerData.properties
        });
    };

    /**
     * Register click event handler
     * @param {Function} callback - Callback function (markerId, markerData, event)
     * @returns {Function} Unsubscribe function
     */
    AoTMarkerManager.prototype.onMarkerClick = function(callback) {
        if (typeof callback !== 'function') {
            console.error('[AoTMarkerManager] Callback must be a function');
            return function() {};
        }
        
        this.eventHandlers.click.push(callback);
        
        var self = this;
        return function() {
            var idx = self.eventHandlers.click.indexOf(callback);
            if (idx > -1) {
                self.eventHandlers.click.splice(idx, 1);
            }
        };
    };

    /**
     * Register hover event handler
     * @param {Function} callback - Callback function (markerId, markerData, type)
     * @returns {Function} Unsubscribe function
     */
    AoTMarkerManager.prototype.onMarkerHover = function(callback) {
        if (typeof callback !== 'function') {
            console.error('[AoTMarkerManager] Callback must be a function');
            return function() {};
        }
        
        this.eventHandlers.hover.push(callback);
        
        var self = this;
        return function() {
            var idx = self.eventHandlers.hover.indexOf(callback);
            if (idx > -1) {
                self.eventHandlers.hover.splice(idx, 1);
            }
        };
    };

    /**
     * Register drag end event handler
     * @param {Function} callback - Callback function (markerId, markerData)
     * @returns {Function} Unsubscribe function
     */
    AoTMarkerManager.prototype.onMarkerDragEnd = function(callback) {
        if (typeof callback !== 'function') {
            console.error('[AoTMarkerManager] Callback must be a function');
            return function() {};
        }
        
        this.eventHandlers.dragend.push(callback);
        
        var self = this;
        return function() {
            var idx = self.eventHandlers.dragend.indexOf(callback);
            if (idx > -1) {
                self.eventHandlers.dragend.splice(idx, 1);
            }
        };
    };

    // ========================================
    // Leaflet Compatibility Layer
    // ========================================

    /**
     * Create a marker (Leaflet-compatible API)
     * @param {Array} latLng - [lat, lng]
     * @param {Object} options - Marker options
     * @returns {Object} Leaflet-compatible marker wrapper
     */
    AoTMarkerManager.prototype.createMarker = function(latLng, options) {
        var self = this;
        options = options || {};
        
        var markerId = this.addMarker({
            lngLat: [latLng[1], latLng[0]], // Leaflet uses [lat, lng]
            type: options.type,
            color: options.color || options.markerColor,
            scale: options.scale,
            icon: options.icon,
            draggable: options.draggable,
            className: options.className,
            properties: options.properties || {}
        });
        
        // Return Leaflet-compatible wrapper
        return {
            _markerId: markerId,
            addTo: function(map) {
                // map parameter is ignored, marker is already added
                return this;
            },
            setLatLng: function(latLng) {
                self.setMarkerPosition(markerId, [latLng[1], latLng[0]]);
                return this;
            },
            getLatLng: function() {
                var data = self.getMarker(markerId);
                if (data) {
                    return { lat: data.lngLat.lat, lng: data.lngLat.lng };
                }
                return null;
            },
            bindPopup: function(content, options) {
                self.addPopup(markerId, {
                    content: content,
                    options: options
                });
                return this;
            },
            openPopup: function() {
                var data = self.getMarker(markerId);
                if (data && data.popup) {
                    self.openPopup(data.popup);
                }
                return this;
            },
            closePopup: function() {
                var data = self.getMarker(markerId);
                if (data && data.popup) {
                    self.closePopup(data.popup);
                }
                return this;
            },
            togglePopup: function() {
                var data = self.getMarker(markerId);
                if (data && data.popup) {
                    self.togglePopup(data.popup);
                }
                return this;
            },
            remove: function() {
                self.removeMarker(markerId);
                return this;
            },
            on: function(event, handler) {
                if (event === 'click') {
                    self.onMarkerClick(function(markerId, data) {
                        handler({ target: this });
                    });
                } else if (event === 'mouseover') {
                    self.onMarkerHover(function(markerId, data, type) {
                        if (type === 'enter') {
                            handler({ type: 'mouseover' });
                        }
                    });
                } else if (event === 'mouseout') {
                    self.onMarkerHover(function(markerId, data, type) {
                        if (type === 'leave') {
                            handler({ type: 'mouseout' });
                        }
                    });
                }
                return this;
            }
        };
    };

    /**
     * Create a marker group (Leaflet-compatible)
     * @param {Object} options - Group options
     * @returns {Object} Leaflet-compatible layer group
     */
    AoTMarkerManager.prototype.createLayerGroup = function(options) {
        var self = this;
        options = options || {};
        
        var groupId = 'leaflet_group_' + Date.now();
        this.addMarkerGroup(groupId, options);
        
        var markers = [];
        
        return {
            _groupId: groupId,
            addLayer: function(layer) {
                if (layer._markerId) {
                    markers.push(layer._markerId);
                    var markerData = self.getMarker(layer._markerId);
                    if (markerData) {
                        self._addMarkerToGroup(layer._markerId, groupId);
                    }
                }
                return this;
            },
            removeLayer: function(layer) {
                if (layer._markerId) {
                    var idx = markers.indexOf(layer._markerId);
                    if (idx > -1) {
                        markers.splice(idx, 1);
                    }
                    self._removeMarkerFromGroup(layer._markerId, groupId);
                }
                return this;
            },
            addTo: function(map) {
                return this;
            },
            remove: function() {
                markers.forEach(function(markerId) {
                    self.removeMarker(markerId);
                });
                self.removeMarkerGroup(groupId);
                return this;
            },
            getLayers: function() {
                return markers.map(function(markerId) {
                    return { _markerId: markerId };
                });
            },
            clearLayers: function() {
                markers.forEach(function(markerId) {
                    self._removeMarkerFromGroup(markerId, groupId);
                });
                markers = [];
                return this;
            }
        };
    };

    // ========================================
    // Convenience Methods for AoT Entities
    // ========================================

    /**
     * Add Site markers
     * @param {Array} sites - Array of site objects with coordinates
     * @returns {Array} Array of marker IDs
     */
    AoTMarkerManager.prototype.addSiteMarkers = function(sites) {
        var self = this;
        var markerIds = [];
        
        // Create site group
        this.addMarkerGroup('sites', { type: 'site', name: 'Sites' });
        
        sites.forEach(function(site) {
            var markerId = this.addMarker({
                lngLat: site.coordinates || site.lngLat || site,
                type: 'site',
                properties: site.properties || site,
                groupId: 'sites'
            });
            markerIds.push(markerId);
            
            // Add popup if content provided
            if (site.name || site.properties) {
                var popupContent = '<div class="aot-popup aot-popup-site">' +
                    '<strong>' + (site.name || site.properties?.name || 'Site') + '</strong>' +
                    (site.description ? '<p>' + site.description + '</p>' : '') +
                    '</div>';
                this.addPopup(markerId, { content: popupContent });
            }
        }, this);
        
        return markerIds;
    };

    /**
     * Add Zone markers
     * @param {Array} zones - Array of zone objects with coordinates
     * @returns {Array} Array of marker IDs
     */
    AoTMarkerManager.prototype.addZoneMarkers = function(zones) {
        var self = this;
        var markerIds = [];
        
        // Create zone group
        this.addMarkerGroup('zones', { type: 'zone', name: 'Zones' });
        
        zones.forEach(function(zone) {
            var markerId = this.addMarker({
                lngLat: zone.coordinates || zone.lngLat || zone,
                type: 'zone',
                properties: zone.properties || zone,
                groupId: 'zones'
            });
            markerIds.push(markerId);
            
            // Add popup if content provided
            if (zone.name || zone.properties) {
                var popupContent = '<div class="aot-popup aot-popup-zone">' +
                    '<strong>' + (zone.name || zone.properties?.name || 'Zone') + '</strong>' +
                    (zone.description ? '<p>' + zone.description + '</p>' : '') +
                    '</div>';
                this.addPopup(markerId, { content: popupContent });
            }
        }, this);
        
        return markerIds;
    };

    /**
     * Add Facility markers
     * @param {Array} facilities - Array of facility objects with coordinates
     * @returns {Array} Array of marker IDs
     */
    AoTMarkerManager.prototype.addFacilityMarkers = function(facilities) {
        var self = this;
        var markerIds = [];
        
        // Create facility group
        this.addMarkerGroup('facilities', { type: 'facility', name: 'Facilities' });
        
        facilities.forEach(function(facility) {
            var markerId = this.addMarker({
                lngLat: facility.coordinates || facility.lngLat || facility,
                type: 'facility',
                properties: facility.properties || facility,
                groupId: 'facilities'
            });
            markerIds.push(markerId);
            
            // Add popup if content provided
            if (facility.name || facility.properties) {
                var popupContent = '<div class="aot-popup aot-popup-facility">' +
                    '<strong>' + (facility.name || facility.properties?.name || 'Facility') + '</strong>' +
                    (facility.description ? '<p>' + facility.description + '</p>' : '') +
                    '</div>';
                this.addPopup(markerId, { content: popupContent });
            }
        }, this);
        
        return markerIds;
    };

    /**
     * Add Device markers
     * @param {Array} devices - Array of device objects with coordinates
     * @returns {Array} Array of marker IDs
     */
    AoTMarkerManager.prototype.addDeviceMarkers = function(devices) {
        var self = this;
        var markerIds = [];
        
        // Create device group
        this.addMarkerGroup('devices', { type: 'device', name: 'Devices' });
        
        devices.forEach(function(device) {
            var markerId = this.addMarker({
                lngLat: device.coordinates || device.lngLat || device,
                type: 'device',
                color: device.color,
                properties: device.properties || device,
                groupId: 'devices'
            });
            markerIds.push(markerId);
            
            // Add popup if content provided
            if (device.name || device.properties) {
                var popupContent = '<div class="aot-popup aot-popup-device">' +
                    '<strong>' + (device.name || device.properties?.name || 'Device') + '</strong>' +
                    (device.status ? '<p>Status: ' + device.status + '</p>' : '') +
                    '</div>';
                this.addPopup(markerId, { content: popupContent });
            }
        }, this);
        
        return markerIds;
    };

    // ========================================
    // Utility Methods
    // ========================================

    /**
     * Clear all markers
     * @returns {AoTMarkerManager}
     */
    AoTMarkerManager.prototype.clearAll = function() {
        var self = this;
        
        // Remove all markers
        this.markers.forEach(function(data, markerId) {
            data.marker.remove();
        });
        this.markers.clear();
        
        // Remove all popups
        this.popups.clear();
        
        // Remove all groups
        this.groups.clear();
        
        this.markerIdCounter = 0;
        this.popupIdCounter = 0;
        
        console.log('[AoTMarkerManager] All markers cleared');
        return this;
    };

    /**
     * Fit map to show all markers
     * @param {number} [padding=50] - Padding in pixels
     * @param {string} [groupId] - Optional group ID to limit to
     * @returns {AoTMarkerManager}
     */
    AoTMarkerManager.prototype.fitBounds = function(padding, groupId) {
        padding = padding || 50;
        
        var bounds;
        var markersToFit;
        
        if (groupId) {
            var group = this.groups.get(groupId);
            if (!group) {
                console.warn('[AoTMarkerManager] Group not found:', groupId);
                return this;
            }
            markersToFit = group.markerIds.map(function(id) {
                return this.markers.get(id);
            }, this);
        } else {
            markersToFit = Array.from(this.markers.values());
        }
        
        if (markersToFit.length === 0) {
            console.warn('[AoTMarkerManager] No markers to fit');
            return this;
        }
        
        // Calculate bounds
        var lngs = [], lats = [];
        markersToFit.forEach(function(data) {
            if (data && data.visible) {
                lngs.push(data.lngLat.lng);
                lats.push(data.lngLat.lat);
            }
        });
        
        if (lngs.length === 0) {
            return this;
        }
        
        bounds = [
            [Math.min.apply(null, lngs), Math.min.apply(null, lats)],
            [Math.max.apply(null, lngs), Math.max.apply(null, lats)]
        ];
        
        this.map.fitBounds(bounds, {
            padding: padding,
            maxZoom: 16
        });
        
        return this;
    };

    /**
     * Get marker count
     * @returns {number}
     */
    AoTMarkerManager.prototype.getMarkerCount = function() {
        return this.markers.size;
    };

    /**
     * Destroy the manager and clean up
     */
    AoTMarkerManager.prototype.destroy = function() {
        // Clear all markers
        this.clearAll();
        
        // Clear event handlers
        this.eventHandlers.click = [];
        this.eventHandlers.hover = [];
        this.eventHandlers.dragend = [];
        
        this.map = null;
        console.log('[AoTMarkerManager] Manager destroyed');
    };

    // Export to global namespace
    window.AoTMarkerManager = AoTMarkerManager;

})(window);
