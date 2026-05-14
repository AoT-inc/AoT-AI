/**
 * aot-maplibre-marker.js
 * Marker and Popup Management Module for MapLibre-GL
 * 
 * This module provides comprehensive marker and popup management for MapLibre:
 * - AoTMarkerManager class for marker lifecycle management
 * - Custom HTML marker support with click/hover events
 * - Popup management with customizable content
 * - Marker grouping for batch operations
 * - Leaflet marker API compatibility layer
 * - Site, Zone, Facility marker visualization
 * 
 * @module AoTMarkerManager
 * @version 1.0.0
 * @requires MapLibre-GL
 * 
 * @example
 * // Initialize marker manager
 * const markerManager = AoTMarkerManager.create(map, {
 *   defaultIcon: true,
 *   clusterMarkers: false
 * });
 * 
 * @example
 * // Add a basic marker
 * markerManager.addMarker('site-1', {
 *   coordinates: [127.0, 37.5],
 *   type: 'site',
 *   label: 'Site A'
 * });
 * 
 * @example
 * // Add marker with popup
 * markerManager.addMarker('zone-1', {
 *   coordinates: [127.1, 37.6],
 *   type: 'zone',
 *   label: 'Zone 1',
 *   popup: {
 *     content: '<h3>Zone 1</h3><p>Status: Active</p>',
 *     maxWidth: 300
 *   }
 * });
 * 
 * @example
 * // Add custom HTML marker
 * markerManager.addCustomMarker('facility-1', {
 *   coordinates: [127.2, 37.7],
 *   html: '<div class="facility-marker"><i class="fa fa-industry"></i></div>',
 *   className: 'custom-facility-marker'
 * });
 */

(function(global) {
  'use strict';

  /**
   * Marker type definitions
   * @readonly
   * @enum {string}
   */
  const MARKER_TYPES = {
    SITE: 'site',
    ZONE: 'zone',
    FACILITY: 'facility',
    CUSTOM: 'custom'
  };

  /**
   * Default marker styles by type
   * @constant {Object}
   */
  const DEFAULT_MARKER_STYLES = {
    site: {
      color: '#2196F3',
      size: 32,
      icon: 'fa-map-marker-alt',
      label: 'Site'
    },
    zone: {
      color: '#4CAF50',
      size: 24,
      icon: 'fa-square',
      label: 'Zone'
    },
    facility: {
      color: '#FF9800',
      size: 20,
      icon: 'fa-industry',
      label: 'Facility'
    }
  };

  /**
   * AoT Marker Manager Namespace
   * @namespace AoTMarkerManager
   */
  const AoTMarkerManager = {
    /** @type {Map<string, MarkerInstance>} Active marker manager instances */
    instances: new Map(),

    /** @type {number} Instance counter */
    _instanceCounter: 0,

    /** @type {Object} Marker type constants */
    MARKER_TYPES: MARKER_TYPES,

    /** @type {Object} Default marker styles */
    DEFAULT_MARKER_STYLES: DEFAULT_MARKER_STYLES
  };

  /**
   * Popup Instance Class
   * Manages individual popup instances
   */
  class PopupInstance {
    /**
     * Create a popup instance
     * @param {maplibregl.Popup} popup - MapLibre popup instance
     * @param {Object} options - Popup configuration
     */
    constructor(popup, options = {}) {
      this.popup = popup;
      this.options = Object.assign({
        closeButton: true,
        closeOnClick: true,
        maxWidth: 300,
        className: 'aot-popup'
      }, options);
      this.markerId = null;
      this.isOpen = false;
    }

    /**
     * Open popup at marker
     * @param {string} markerId - Associated marker ID
     */
    open(markerId) {
      this.markerId = markerId;
      this.isOpen = true;
    }

    /**
     * Close popup
     */
    close() {
      this.isOpen = false;
      this.markerId = null;
    }

    /**
     * Check if popup is currently open
     * @returns {boolean}
     */
    isPopupOpen() {
      return this.isOpen;
    }

    /**
     * Remove popup from map
     */
    remove() {
      if (this.popup && this.popup.remove) {
        this.popup.remove();
      }
      this.popup = null;
      this.isOpen = false;
    }
  }

  /**
   * Marker Instance Class
   * Manages individual marker instances
   */
  class MarkerInstance {
    /**
     * Create a marker instance
     * @param {string} id - Unique marker identifier
     * @param {maplibregl.Marker} marker - MapLibre marker instance
     * @param {Object} options - Marker configuration
     */
    constructor(id, marker, options = {}) {
      this.id = id;
      this.marker = marker;
      this.options = Object.assign({
        type: 'custom',
        label: '',
        coordinates: [0, 0],
        draggable: false,
        clickable: true,
        hoverable: true
      }, options);
      this.popup = null;
      this.groupId = null;
      this._eventHandlers = {
        click: [],
        mouseover: [],
        mouseout: []
      };
    }

    /**
     * Attach event handler
     * @param {string} eventType - Event type (click, mouseover, mouseout)
     * @param {Function} handler - Event handler function
     */
    on(eventType, handler) {
      if (this._eventHandlers[eventType]) {
        this._eventHandlers[eventType].push(handler);
      }
    }

    /**
     * Remove event handler
     * @param {string} eventType - Event type
     * @param {Function} handler - Event handler to remove
     */
    off(eventType, handler) {
      if (this._eventHandlers[eventType]) {
        const index = this._eventHandlers[eventType].indexOf(handler);
        if (index > -1) {
          this._eventHandlers[eventType].splice(index, 1);
        }
      }
    }

    /**
     * Trigger event handlers
     * @param {string} eventType - Event type
     * @param {Object} data - Event data
     * @private
     */
    _triggerEvent(eventType, data) {
      if (this._eventHandlers[eventType]) {
        this._eventHandlers[eventType].forEach(function(handler) {
          try {
            handler(data);
          } catch (e) {
            console.error('[MarkerInstance] Event handler error:', e);
          }
        });
      }
    }

    /**
     * Get marker coordinates
     * @returns {Array<number>} [lng, lat]
     */
    getCoordinates() {
      if (this.marker) {
        return this.marker.getLngLat().toArray();
      }
      return this.options.coordinates;
    }

    /**
     * Set marker coordinates
     * @param {Array<number>} coordinates - [lng, lat]
     */
    setCoordinates(coordinates) {
      if (this.marker) {
        this.marker.setLngLat(coordinates);
        this.options.coordinates = coordinates;
      }
    }

    /**
     * Get associated popup
     * @returns {PopupInstance|null}
     */
    getPopup() {
      return this.popup;
    }

    /**
     * Set associated popup
     * @param {PopupInstance} popup - Popup instance
     */
    setPopup(popup) {
      this.popup = popup;
    }

    /**
     * Remove marker from map
     */
    remove() {
      if (this.marker) {
        this.marker.remove();
        this.marker = null;
      }
      if (this.popup) {
        this.popup.remove();
        this.popup = null;
      }
    }
  }

  /**
   * Marker Instance Class
   * Manages markers for a single MapLibre map
   */
  class MarkerInstanceManager {
    /**
     * Create a new marker manager instance
     * @param {maplibregl.Map} map - MapLibre map instance
     * @param {Object} options - Configuration options
     * @param {boolean} [options.defaultIcons=true] - Use default icons
     * @param {boolean} [options.clusterMarkers=false] - Enable marker clustering
     * @param {number} [options.clusterRadius=50] - Cluster radius in pixels
     * @param {boolean} [options.showLabels=true] - Show marker labels
     * @param {Object} [options.defaultStyles] - Custom default styles
     */
    constructor(map, options = {}) {
      this.id = 'marker_' + (AoTMarkerManager._instanceCounter++);
      this.map = map;
      this.options = Object.assign({
        defaultIcons: true,
        clusterMarkers: false,
        clusterRadius: 50,
        showLabels: true,
        defaultStyles: DEFAULT_MARKER_STYLES
      }, options);

      /** @type {Map<string, MarkerInstance>} Managed markers */
      this.markers = new Map();

      /** @type {Map<string, PopupInstance>} Managed popups */
      this.popups = new Map();

      /** @type {Map<string, string>} Marker groups */
      this.groups = new Map();

      /** @type {Map<string, string>} Markers in groups */
      this.groupedMarkers = new Map();

      /** @type {HTMLElement} Marker container */
      this._container = null;

      /** @type {Function} Bound click handler */
      this._boundClickHandler = this._handleMarkerClick.bind(this);
      this._boundHoverHandlers = this._handleMarkerHover.bind(this);

      console.log('[AoTMarkerManager] Instance created:', this.id);
    }

    /**
     * Initialize the marker container
     * @private
     */
    _initContainer() {
      if (!this._container) {
        this._container = document.createElement('div');
        this._container.id = 'aot-marker-container-' + this.id;
        this._container.className = 'aot-marker-container';
        this._container.style.position = 'absolute';
        this._container.style.top = '0';
        this._container.style.left = '0';
        this._container.style.pointerEvents = 'none';
        
        // Add to map
        if (this.map && this.map.getContainer) {
          const mapContainer = this.map.getContainer();
          mapContainer.appendChild(this._container);
        }
      }
    }

    /**
     * Create a default icon element
     * @param {string} type - Marker type
     * @param {Object} style - Marker style options
     * @returns {HTMLElement} Icon element
     * @private
     */
    _createDefaultIcon(type, style) {
      const defaults = this.options.defaultStyles[type] || DEFAULT_MARKER_STYLES.facility;
      const markerStyle = Object.assign({}, defaults, style);

      const iconEl = document.createElement('div');
      iconEl.className = 'aot-marker-icon aot-marker-' + type;
      iconEl.style.cssText = `
        width: ${markerStyle.size}px;
        height: ${markerStyle.size}px;
        background-color: ${markerStyle.color};
        border: 2px solid #ffffff;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 2px 6px rgba(0,0,0,0.3);
        cursor: pointer;
        transition: transform 0.2s ease;
      `;

      if (markerStyle.icon) {
        const iconInner = document.createElement('i');
        iconInner.className = 'fa ' + markerStyle.icon;
        iconInner.style.color = '#ffffff';
        iconInner.style.fontSize = (markerStyle.size * 0.5) + 'px';
        iconEl.appendChild(iconInner);
      }

      return iconEl;
    }

    /**
     * Create a custom HTML marker element
     * @param {string} html - Custom HTML content
     * @param {string} className - CSS class name
     * @param {Object} style - Style options
     * @returns {HTMLElement} Marker element
     * @private
     */
    _createCustomMarkerElement(html, className, style = {}) {
      const el = document.createElement('div');
      el.className = 'aot-custom-marker ' + (className || '');
      el.innerHTML = html;
      el.style.cssText = Object.assign({
        cursor: 'pointer',
        transition: 'transform 0.2s ease'
      }, style);

      return el;
    }

    /**
     * Handle marker click event
     * @param {Object} data - Event data
     * @private
     */
    _handleMarkerClick(data) {
      const markerId = data.markerId;
      const markerInstance = this.markers.get(markerId);
      
      if (markerInstance) {
        markerInstance._triggerEvent('click', {
          markerId: markerId,
          coordinates: markerInstance.getCoordinates(),
          options: markerInstance.options
        });

        // Toggle popup if present
        if (markerInstance.popup) {
          if (markerInstance.popup.isOpen) {
            markerInstance.popup.popup.remove();
            markerInstance.popup.close();
          } else {
            markerInstance.popup.popup.setLngLat(markerInstance.getCoordinates()).addTo(this.map);
            markerInstance.popup.open(markerId);
          }
        }
      }
    }

    /**
     * Handle marker hover events
     * @param {Object} data - Event data
     * @private
     */
    _handleMarkerHover(data) {
      const markerId = data.markerId;
      const markerInstance = this.markers.get(markerId);

      if (markerInstance) {
        if (data.type === 'mouseover') {
          markerInstance._triggerEvent('mouseover', {
            markerId: markerId,
            coordinates: markerInstance.getCoordinates(),
            element: data.element
          });
          if (data.element) {
            data.element.style.transform = 'scale(1.2)';
            // Keep below tool buttons (z-index 20) — labels must not cover tools
            data.element.style.zIndex = '5';
          }
        } else if (data.type === 'mouseout') {
          markerInstance._triggerEvent('mouseout', {
            markerId: markerId,
            coordinates: markerInstance.getCoordinates(),
            element: data.element
          });
          if (data.element) {
            data.element.style.transform = 'scale(1)';
            data.element.style.zIndex = '';
          }
        }
      }
    }

    /**
     * Add a marker to the map
     * @param {string} id - Unique marker identifier
     * @param {Object} options - Marker configuration
     * @param {Array<number>} options.coordinates - [lng, lat]
     * @param {string} [options.type='custom'] - Marker type (site, zone, facility, custom)
     * @param {string} [options.label=''] - Marker label
     * @param {HTMLElement} [options.element] - Custom DOM element (overrides default icon)
     * @param {string} [options.html] - Custom HTML for marker
     * @param {string} [options.className] - CSS class for custom marker
     * @param {boolean} [options.draggable=false] - Enable marker dragging
     * @param {boolean} [options.clickable=true] - Enable click events
     * @param {boolean} [options.hoverable=true] - Enable hover events
     * @param {Object} [options.style] - Custom style options
     * @param {Object} [options.popup] - Popup configuration
     * @returns {MarkerInstance} Marker instance
     */
    addMarker(id, options) {
      // Check if marker already exists
      if (this.markers.has(id)) {
        console.warn('[AoTMarkerManager] Marker ' + id + ' already exists');
        return this.markers.get(id);
      }

      // Create marker element
      let element;
      if (options.element) {
        element = options.element;
      } else if (options.html) {
        element = this._createCustomMarkerElement(options.html, options.className, options.style);
      } else {
        element = this._createDefaultIcon(options.type || 'custom', options.style);
      }

      // Add label if enabled
      if (this.options.showLabels && options.label) {
        const labelEl = document.createElement('div');
        labelEl.className = 'aot-marker-label';
        labelEl.textContent = options.label;
        labelEl.style.cssText = `
          position: absolute;
          top: 100%;
          left: 50%;
          transform: translateX(-50%);
          margin-top: 4px;
          font-size: 11px;
          font-weight: 500;
          color: #333;
          white-space: nowrap;
          text-shadow: 0 1px 2px rgba(255,255,255,0.8);
        `;
        element.appendChild(labelEl);
      }

      // Create MapLibre marker
      const markerOptions = {
        element: element,
        anchor: 'center',
        draggable: options.draggable || false
      };

      const marker = new maplibregl.Marker(markerOptions)
        .setLngLat(options.coordinates)
        .addTo(this.map);

      // Create marker instance
      const markerInstance = new MarkerInstance(id, marker, {
        type: options.type || 'custom',
        label: options.label || '',
        coordinates: options.coordinates,
        draggable: options.draggable || false,
        clickable: options.clickable !== false,
        hoverable: options.hoverable !== false
      });

      // Attach click event
      if (markerInstance.options.clickable) {
        element.addEventListener('click', function(e) {
          e.stopPropagation();
          this._handleMarkerClick({
            markerId: id,
            element: element
          });
        }.bind(this));
      }

      // Attach hover events
      if (markerInstance.options.hoverable) {
        element.addEventListener('mouseover', function(e) {
          this._handleMarkerHover({
            markerId: id,
            type: 'mouseover',
            element: element
          });
        }.bind(this));

        element.addEventListener('mouseout', function(e) {
          this._handleMarkerHover({
            markerId: id,
            type: 'mouseout',
            element: element
          });
        }.bind(this));
      }

      // Attach drag events
      if (options.draggable) {
        marker.on('dragstart', function() {
          markerInstance._triggerEvent('dragstart', { markerId: id });
        });
        marker.on('drag', function() {
          markerInstance._triggerEvent('drag', {
            markerId: id,
            coordinates: marker.getLngLat().toArray()
          });
        });
        marker.on('dragend', function() {
          markerInstance._triggerEvent('dragend', {
            markerId: id,
            coordinates: marker.getLngLat().toArray()
          });
        });
      }

      // Add popup if configured
      if (options.popup) {
        const popupInstance = this.addPopup(id + '_popup', {
          coordinates: options.coordinates,
          content: options.popup.content || '',
          maxWidth: options.popup.maxWidth || 300,
          closeButton: options.popup.closeButton !== false,
          closeOnClick: options.popup.closeOnClick !== false
        });
        markerInstance.setPopup(popupInstance);
      }

      // Store marker
      this.markers.set(id, markerInstance);

      console.log('[AoTMarkerManager] Marker added:', id);
      return markerInstance;
    }

    /**
     * Remove a marker from the map
     * @param {string} id - Marker identifier
     * @returns {boolean} Success status
     */
    removeMarker(id) {
      const markerInstance = this.markers.get(id);
      if (!markerInstance) {
        console.warn('[AoTMarkerManager] Marker ' + id + ' not found');
        return false;
      }

      // Remove from group if in one
      if (markerInstance.groupId) {
        this.removeFromGroup(id);
      }

      // Remove marker
      markerInstance.remove();
      this.markers.delete(id);

      // Remove associated popup
      const popupId = id + '_popup';
      if (this.popups.has(popupId)) {
        this.removePopup(popupId);
      }

      console.log('[AoTMarkerManager] Marker removed:', id);
      return true;
    }

    /**
     * Get a marker instance by ID
     * @param {string} id - Marker identifier
     * @returns {MarkerInstance|null}
     */
    getMarker(id) {
      return this.markers.get(id) || null;
    }

    /**
     * Get all markers
     * @returns {Array<MarkerInstance>}
     */
    getAllMarkers() {
      return Array.from(this.markers.values());
    }

    /**
     * Check if marker exists
     * @param {string} id - Marker identifier
     * @returns {boolean}
     */
    hasMarker(id) {
      return this.markers.has(id);
    }

    /**
     * Update marker coordinates
     * @param {string} id - Marker identifier
     * @param {Array<number>} coordinates - New [lng, lat]
     * @returns {boolean} Success status
     */
    updateMarkerCoordinates(id, coordinates) {
      const markerInstance = this.markers.get(id);
      if (!markerInstance) {
        console.warn('[AoTMarkerManager] Marker ' + id + ' not found');
        return false;
      }

      markerInstance.setCoordinates(coordinates);
      return true;
    }

    /**
     * Add a marker group
     * @param {string} groupId - Group identifier
     * @param {string[]} markerIds - Array of marker IDs to include in group
     * @param {Object} [options] - Group options
     * @param {string} [options.label] - Group label
     * @param {string} [options.color] - Group color
     * @returns {boolean} Success status
     */
    addMarkerGroup(groupId, markerIds, options = {}) {
      if (this.groups.has(groupId)) {
        console.warn('[AoTMarkerManager] Group ' + groupId + ' already exists');
        return false;
      }

      // Validate marker IDs
      const validMarkerIds = [];
      markerIds.forEach(function(markerId) {
        if (this.markers.has(markerId)) {
          validMarkerIds.push(markerId);
          const markerInstance = this.markers.get(markerId);
          markerInstance.groupId = groupId;
          this.groupedMarkers.set(markerId, groupId);
        } else {
          console.warn('[AoTMarkerManager] Marker ' + markerId + ' not found, skipping');
        }
      }.bind(this));

      if (validMarkerIds.length === 0) {
        console.warn('[AoTMarkerManager] No valid markers for group ' + groupId);
        return false;
      }

      // Store group
      this.groups.set(groupId, {
        id: groupId,
        markerIds: validMarkerIds,
        label: options.label || groupId,
        color: options.color || '#2196F3',
        visible: true
      });

      console.log('[AoTMarkerManager] Group added:', groupId, 'with', validMarkerIds.length, 'markers');
      return true;
    }

    /**
     * Remove a marker from its group
     * @param {string} markerId - Marker identifier
     * @returns {boolean} Success status
     */
    removeFromGroup(markerId) {
      const groupId = this.groupedMarkers.get(markerId);
      if (!groupId) {
        return false;
      }

      const group = this.groups.get(groupId);
      if (group) {
        group.markerIds = group.markerIds.filter(function(id) { return id !== markerId; });
        if (group.markerIds.length === 0) {
          this.groups.delete(groupId);
        }
      }

      const markerInstance = this.markers.get(markerId);
      if (markerInstance) {
        markerInstance.groupId = null;
      }

      this.groupedMarkers.delete(markerId);
      return true;
    }

    /**
     * Remove a marker group (keeps markers)
     * @param {string} groupId - Group identifier
     * @returns {boolean} Success status
     */
    removeGroup(groupId) {
      const group = this.groups.get(groupId);
      if (!group) {
        console.warn('[AoTMarkerManager] Group ' + groupId + ' not found');
        return false;
      }

      // Remove group reference from markers
      group.markerIds.forEach(function(markerId) {
        this.groupedMarkers.delete(markerId);
        const markerInstance = this.markers.get(markerId);
        if (markerInstance) {
          markerInstance.groupId = null;
        }
      }.bind(this));

      this.groups.delete(groupId);
      console.log('[AoTMarkerManager] Group removed:', groupId);
      return true;
    }

    /**
     * Get markers in a group
     * @param {string} groupId - Group identifier
     * @returns {Array<MarkerInstance>}
     */
    getGroupMarkers(groupId) {
      const group = this.groups.get(groupId);
      if (!group) {
        return [];
      }

      return group.markerIds
        .map(function(id) { return this.markers.get(id); }.bind(this))
        .filter(function(m) { return m !== undefined; });
    }

    /**
     * Set group visibility
     * @param {string} groupId - Group identifier
     * @param {boolean} visible - Show/hide group markers
     * @returns {boolean} Success status
     */
    setGroupVisibility(groupId, visible) {
      const group = this.groups.get(groupId);
      if (!group) {
        console.warn('[AoTMarkerManager] Group ' + groupId + ' not found');
        return false;
      }

      group.visible = visible;
      group.markerIds.forEach(function(markerId) {
        const markerInstance = this.markers.get(markerId);
        if (markerInstance && markerInstance.marker) {
          markerInstance.marker.getElement().style.display = visible ? '' : 'none';
        }
      }.bind(this));

      console.log('[AoTMarkerManager] Group ' + groupId + ' visibility:', visible);
      return true;
    }

    /**
     * Add a popup to a marker
     * @param {string} id - Popup identifier
     * @param {Object} options - Popup configuration
     * @param {Array<number>} options.coordinates - [lng, lat]
     * @param {string} options.content - HTML content
     * @param {number} [options.maxWidth=300] - Maximum width
     * @param {boolean} [options.closeButton=true] - Show close button
     * @param {boolean} [options.closeOnClick=true] - Close on map click
     * @returns {PopupInstance} Popup instance
     */
    addPopup(id, options) {
      if (this.popups.has(id)) {
        console.warn('[AoTMarkerManager] Popup ' + id + ' already exists');
        return this.popups.get(id);
      }

      const popupOptions = {
        closeButton: options.closeButton !== false,
        closeOnClick: options.closeOnClick !== false,
        maxWidth: options.maxWidth || 300,
        className: 'aot-popup'
      };

      const popup = new maplibregl.Popup(popupOptions)
        .setHTML(options.content || '');

      const popupInstance = new PopupInstance(popup, popupOptions);

      // Add close handler
      popup.on('close', function() {
        popupInstance.close();
      });

      this.popups.set(id, popupInstance);
      console.log('[AoTMarkerManager] Popup added:', id);
      return popupInstance;
    }

    /**
     * Remove a popup
     * @param {string} id - Popup identifier
     * @returns {boolean} Success status
     */
    removePopup(id) {
      const popupInstance = this.popups.get(id);
      if (!popupInstance) {
        console.warn('[AoTMarkerManager] Popup ' + id + ' not found');
        return false;
      }

      popupInstance.remove();
      this.popups.delete(id);
      console.log('[AoTMarkerManager] Popup removed:', id);
      return true;
    }

    /**
     * Update popup content
     * @param {string} id - Popup identifier
     * @param {string} content - New HTML content
     * @returns {boolean} Success status
     */
    updatePopupContent(id, content) {
      const popupInstance = this.popups.get(id);
      if (!popupInstance) {
        console.warn('[AoTMarkerManager] Popup ' + id + ' not found');
        return false;
      }

      if (popupInstance.popup) {
        popupInstance.popup.setHTML(content);
      }
      return true;
    }

    /**
     * Show popup for a marker
     * @param {string} markerId - Marker identifier
     * @returns {boolean} Success status
     */
    showPopup(markerId) {
      const markerInstance = this.markers.get(markerId);
      if (!markerInstance) {
        console.warn('[AoTMarkerManager] Marker ' + markerId + ' not found');
        return false;
      }

      const popupInstance = markerInstance.getPopup();
      if (!popupInstance) {
        console.warn('[AoTMarkerManager] No popup attached to marker ' + markerId);
        return false;
      }

      const coordinates = markerInstance.getCoordinates();
      popupInstance.popup.setLngLat(coordinates).addTo(this.map);
      popupInstance.open(markerId);
      return true;
    }

    /**
     * Hide popup for a marker
     * @param {string} markerId - Marker identifier
     * @returns {boolean} Success status
     */
    hidePopup(markerId) {
      const markerInstance = this.markers.get(markerId);
      if (!markerInstance) {
        console.warn('[AoTMarkerManager] Marker ' + markerId + ' not found');
        return false;
      }

      const popupInstance = markerInstance.getPopup();
      if (!popupInstance) {
        return false;
      }

      popupInstance.popup.remove();
      popupInstance.close();
      return true;
    }

    /**
     * Add custom HTML marker
     * @param {string} id - Marker identifier
     * @param {Object} options - Marker configuration
     * @param {Array<number>} options.coordinates - [lng, lat]
     * @param {string} options.html - Custom HTML content
     * @param {string} [options.className] - CSS class
     * @param {boolean} [options.draggable=false] - Enable dragging
     * @param {Object} [options.style] - Custom CSS styles
     * @returns {MarkerInstance} Marker instance
     */
    addCustomMarker(id, options) {
      return this.addMarker(id, Object.assign({}, options, {
        type: 'custom',
        html: options.html
      }));
    }

    /**
     * Add Site marker
     * @param {string} id - Marker identifier
     * @param {Object} options - Marker configuration
     * @param {Array<number>} options.coordinates - [lng, lat]
     * @param {string} [options.label] - Site name
     * @param {Object} [options.popup] - Popup configuration
     * @returns {MarkerInstance} Marker instance
     */
    addSiteMarker(id, options) {
      return this.addMarker(id, Object.assign({}, options, {
        type: MARKER_TYPES.SITE,
        label: options.label || 'Site'
      }));
    }

    /**
     * Add Zone marker
     * @param {string} id - Marker identifier
     * @param {Object} options - Marker configuration
     * @param {Array<number>} options.coordinates - [lng, lat]
     * @param {string} [options.label] - Zone name
     * @param {Object} [options.popup] - Popup configuration
     * @returns {MarkerInstance} Marker instance
     */
    addZoneMarker(id, options) {
      return this.addMarker(id, Object.assign({}, options, {
        type: MARKER_TYPES.ZONE,
        label: options.label || 'Zone'
      }));
    }

    /**
     * Add Facility marker
     * @param {string} id - Marker identifier
     * @param {Object} options - Marker configuration
     * @param {Array<number>} options.coordinates - [lng, lat]
     * @param {string} [options.label] - Facility name
     * @param {Object} [options.popup] - Popup configuration
     * @returns {MarkerInstance} Marker instance
     */
    addFacilityMarker(id, options) {
      return this.addMarker(id, Object.assign({}, options, {
        type: MARKER_TYPES.FACILITY,
        label: options.label || 'Facility'
      }));
    }

    /**
     * Add multiple Site markers
     * @param {Array<Object>} sites - Array of site objects
     * @param {string} sites[].id - Site ID
     * @param {Array<number>} sites[].coordinates - [lng, lat]
     * @param {string} [sites[].label] - Site name
     * @param {string} [sites[].data] - Additional data
     * @returns {string[]} Array of created marker IDs
     */
    addSiteMarkers(sites) {
      const createdIds = [];
      sites.forEach(function(site) {
        try {
          const marker = this.addSiteMarker(site.id, {
            coordinates: site.coordinates,
            label: site.label,
            popup: site.popup,
            data: site.data
          });
          createdIds.push(site.id);
        } catch (e) {
          console.error('[AoTMarkerManager] Error adding site marker:', site.id, e);
        }
      }.bind(this));
      return createdIds;
    }

    /**
     * Add multiple Zone markers
     * @param {Array<Object>} zones - Array of zone objects
     * @param {string} zones[].id - Zone ID
     * @param {Array<number>} zones[].coordinates - [lng, lat]
     * @param {string} [zones[].label] - Zone name
     * @param {string} [zones[].data] - Additional data
     * @returns {string[]} Array of created marker IDs
     */
    addZoneMarkers(zones) {
      const createdIds = [];
      zones.forEach(function(zone) {
        try {
          const marker = this.addZoneMarker(zone.id, {
            coordinates: zone.coordinates,
            label: zone.label,
            popup: zone.popup,
            data: zone.data
          });
          createdIds.push(zone.id);
        } catch (e) {
          console.error('[AoTMarkerManager] Error adding zone marker:', zone.id, e);
        }
      }.bind(this));
      return createdIds;
    }

    /**
     * Add multiple Facility markers
     * @param {Array<Object>} facilities - Array of facility objects
     * @param {string} facilities[].id - Facility ID
     * @param {Array<number>} facilities[].coordinates - [lng, lat]
     * @param {string} [facilities[].label] - Facility name
     * @param {string} [facilities[].data] - Additional data
     * @returns {string[]} Array of created marker IDs
     */
    addFacilityMarkers(facilities) {
      const createdIds = [];
      facilities.forEach(function(facility) {
        try {
          const marker = this.addFacilityMarker(facility.id, {
            coordinates: facility.coordinates,
            label: facility.label,
            popup: facility.popup,
            data: facility.data
          });
          createdIds.push(facility.id);
        } catch (e) {
          console.error('[AoTMarkerManager] Error adding facility marker:', facility.id, e);
        }
      }.bind(this));
      return createdIds;
    }

    /**
     * Clear all markers
     * @returns {number} Number of markers removed
     */
    clearAllMarkers() {
      const count = this.markers.size;
      const markerIds = Array.from(this.markers.keys());
      markerIds.forEach(function(id) {
        this.removeMarker(id);
      }.bind(this));
      console.log('[AoTMarkerManager] Cleared', count, 'markers');
      return count;
    }

    /**
     * Get marker count
     * @returns {number}
     */
    getMarkerCount() {
      return this.markers.size;
    }

    /**
     * Get marker statistics
     * @returns {Object} Statistics object
     */
    getStats() {
      const stats = {
        totalMarkers: this.markers.size,
        byType: {},
        byGroup: {},
        markers: []
      };

      // Count by type
      this.markers.forEach(function(marker) {
        const type = marker.options.type || 'custom';
        stats.byType[type] = (stats.byType[type] || 0) + 1;
      });

      // Count by group
      this.groups.forEach(function(group, groupId) {
        stats.byGroup[groupId] = group.markerIds.length;
      });

      // List all markers
      this.markers.forEach(function(marker) {
        stats.markers.push({
          id: marker.id,
          type: marker.options.type,
          coordinates: marker.getCoordinates(),
          groupId: marker.groupId,
          hasPopup: !!marker.popup
        });
      });

      return stats;
    }

    /**
     * Fit map to show all markers
     * @param {Object} [options] - Fit bounds options
     * @param {number} [options.padding=50] - Padding in pixels
     * @param {number} [options.maxZoom=15] - Maximum zoom level
     * @returns {boolean} Success status
     */
    fitBounds(options = {}) {
      if (this.markers.size === 0) {
        console.warn('[AoTMarkerManager] No markers to fit bounds');
        return false;
      }

      const bounds = new maplibregl.LngLatBounds();
      let hasValidBounds = false;

      this.markers.forEach(function(marker) {
        const coords = marker.getCoordinates();
        if (Array.isArray(coords) && coords.length >= 2) {
          bounds.extend(coords);
          hasValidBounds = true;
        }
      });

      if (!hasValidBounds) {
        console.warn('[AoTMarkerManager] No valid coordinates for bounds');
        return false;
      }

      this.map.fitBounds(bounds, {
        padding: options.padding || 50,
        maxZoom: options.maxZoom || 15
      });

      console.log('[AoTMarkerManager] Fitted bounds to', this.markers.size, 'markers');
      return true;
    }

    /**
     * Destroy the marker manager
     */
    destroy() {
      // Clear all markers
      this.clearAllMarkers();

      // Clear groups
      this.groups.clear();
      this.groupedMarkers.clear();

      // Remove container
      if (this._container && this._container.parentNode) {
        this._container.parentNode.removeChild(this._container);
      }
      this._container = null;

      // Remove from instances
      AoTMarkerManager.instances.delete(this.id);

      this.map = null;
      console.log('[AoTMarkerManager] Instance destroyed:', this.id);
    }
  }

  /**
   * Create a new marker manager instance
   * @param {maplibregl.Map} map - MapLibre map instance
   * @param {Object} [options] - Configuration options
   * @returns {MarkerInstanceManager} Marker manager instance
   */
  AoTMarkerManager.create = function(map, options) {
    if (!map) {
      throw new Error('[AoTMarkerManager] MapLibre map instance is required');
    }

    const instance = new MarkerInstanceManager(map, options);
    this.instances.set(instance.id, instance);
    console.log('[AoTMarkerManager] Created new instance:', instance.id);
    return instance;
  };

  /**
   * Get a marker manager instance by ID
   * @param {string} id - Instance ID
   * @returns {MarkerInstanceManager|null}
   */
  AoTMarkerManager.get = function(id) {
    return this.instances.get(id) || null;
  };

  /**
   * Get all active marker manager instances
   * @returns {Array<MarkerInstanceManager>}
   */
  AoTMarkerManager.getAll = function() {
    return Array.from(this.instances.values());
  };

  /**
   * Destroy all marker manager instances
   */
  AoTMarkerManager.destroyAll = function() {
    this.instances.forEach(function(instance) {
      instance.destroy();
    });
    console.log('[AoTMarkerManager] All instances destroyed');
  };

  // ============================================
  // Leaflet Marker API Compatibility Layer
  // ============================================

  /**
   * Leaflet-compatible Marker class
   * Provides similar API to L.marker() for easy migration
   */
  class LeafletCompatibleMarker {
    /**
     * Create a Leaflet-compatible marker
     * @param {Array} coordinates - [lat, lng] (Leaflet order)
     * @param {Object} options - Marker options
     */
    constructor(coordinates, options = {}) {
      this._latlng = coordinates; // [lat, lng]
      this._options = Object.assign({
        draggable: false,
        clickable: true,
        title: '',
        alt: ''
      }, options);
      this._map = null;
      this._markerManager = null;
      this._id = 'leaflet_marker_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
      this._eventHandlers = {};
      this._popup = null;
    }

    /**
     * Add marker to map
     * @param {maplibregl.Map} map - MapLibre map instance
     * @returns {LeafletCompatibleMarker}
     */
    addTo(map) {
      if (!this._markerManager) {
        // Get or create marker manager for this map
        const mapId = map._aotMarkerManagerId;
        if (mapId) {
          this._markerManager = AoTMarkerManager.get(mapId);
        }
        
        if (!this._markerManager) {
          this._markerManager = AoTMarkerManager.create(map);
          map._aotMarkerManagerId = this._markerManager.id;
        }
      }

      // Convert [lat, lng] to [lng, lat] for MapLibre
      const maplibreCoords = [this._latlng[1], this._latlng[0]];

      // Add marker to manager
      this._markerManager.addMarker(this._id, {
        coordinates: maplibreCoords,
        type: this._options.type || 'custom',
        draggable: this._options.draggable,
        clickable: this._options.clickable,
        popup: this._popup ? { content: this._popup } : undefined
      });

      this._map = map;
      return this;
    }

    /**
     * Set marker coordinates
     * @param {Array} latlng - [lat, lng]
     * @returns {LeafletCompatibleMarker}
     */
    setLatLng(latlng) {
      this._latlng = latlng;
      if (this._markerManager && this._map) {
        const maplibreCoords = [latlng[1], latlng[0]];
        this._markerManager.updateMarkerCoordinates(this._id, maplibreCoords);
      }
      return this;
    }

    /**
     * Get marker coordinates
     * @returns {Array} [lat, lng]
     */
    getLatLng() {
      return this._latlng;
    }

    /**
     * Set icon
     * @param {Object} icon - Icon configuration
     * @returns {LeafletCompatibleMarker}
     */
    setIcon(icon) {
      if (icon && icon.options) {
        this._options.iconOptions = icon.options;
      }
      // Note: Full icon implementation would require recreating the marker
      return this;
    }

    /**
     * Bind popup
     * @param {string} content - Popup HTML content
     * @returns {LeafletCompatibleMarker}
     */
    bindPopup(content) {
      this._popup = content;
      if (this._markerManager) {
        const marker = this._markerManager.getMarker(this._id);
        if (marker) {
          const popup = this._markerManager.addPopup(this._id + '_popup', {
            coordinates: [this._latlng[1], this._latlng[0]],
            content: content
          });
          marker.setPopup(popup);
        }
      }
      return this;
    }

    /**
     * Open bound popup
     * @returns {LeafletCompatibleMarker}
     */
    openPopup() {
      if (this._markerManager) {
        this._markerManager.showPopup(this._id);
      }
      return this;
    }

    /**
     * Close bound popup
     * @returns {LeafletCompatibleMarker}
     */
    closePopup() {
      if (this._markerManager) {
        this._markerManager.hidePopup(this._id);
      }
      return this;
    }

    /**
     * Add event listener
     * @param {string} type - Event type
     * @param {Function} handler - Event handler
     * @returns {LeafletCompatibleMarker}
     */
    on(type, handler) {
      if (!this._eventHandlers[type]) {
        this._eventHandlers[type] = [];
      }
      this._eventHandlers[type].push(handler);

      if (this._markerManager) {
        const marker = this._markerManager.getMarker(this._id);
        if (marker) {
          marker.on(type, handler);
        }
      }
      return this;
    }

    /**
     * Remove event listener
     * @param {string} type - Event type
     * @param {Function} handler - Event handler
     * @returns {LeafletCompatibleMarker}
     */
    off(type, handler) {
      if (this._eventHandlers[type]) {
        const index = this._eventHandlers[type].indexOf(handler);
        if (index > -1) {
          this._eventHandlers[type].splice(index, 1);
        }
      }

      if (this._markerManager) {
        const marker = this._markerManager.getMarker(this._id);
        if (marker) {
          marker.off(type, handler);
        }
      }
      return this;
    }

    /**
     * Enable dragging
     * @returns {LeafletCompatibleMarker}
     */
    draggable() {
      this._options.draggable = true;
      return this;
    }

    /**
     * Remove marker from map
     */
    remove() {
      if (this._markerManager) {
        this._markerManager.removeMarker(this._id);
      }
      this._map = null;
      this._markerManager = null;
    }
  }

  /**
   * Create a Leaflet-compatible marker
   * Mimics L.marker() API
   * @param {Array} coordinates - [lat, lng]
   * @param {Object} options - Marker options
   * @returns {LeafletCompatibleMarker}
   */
  AoTMarkerManager.marker = function(coordinates, options) {
    return new LeafletCompatibleMarker(coordinates, options);
  };

  /**
   * Create a marker icon
   * Mimics L.icon() API
   * @param {Object} options - Icon options
   * @returns {Object} Icon object
   */
  AoTMarkerManager.icon = function(options) {
    return {
      options: Object.assign({
        iconUrl: options.iconUrl || '',
        iconSize: options.iconSize || [25, 41],
        iconAnchor: options.iconAnchor || [12, 41],
        popupAnchor: options.popupAnchor || [0, -30]
      }, options)
    };
  };

  // Export to global scope
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = AoTMarkerManager;
  } else {
    global.AoTMarkerManager = AoTMarkerManager;
  }

})(typeof window !== 'undefined' ? window : this);
