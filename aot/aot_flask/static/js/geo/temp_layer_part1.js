/**
 * AoT Leaflet Compatibility Layer (MapLibre Backend)
 * Provides Leaflet-compatible L.* API using MapLibre GL as the underlying engine.
 * 
 * @version 1.3 - Added L_Class.include, MapLibre polyfills at top
 */

(function(global) {
    'use strict';

    // ============================================================
    // INITIALIZE GLOBAL L NAMESPACE - MUST be first
    // ============================================================
    global.L = global.L || {};

    // ============================================================
    // MAPLIBRE PROTOTYPE POLYFILLS - MUST be at top before any L_Class usage
    // ============================================================
    
    if (typeof maplibregl !== 'undefined') {
        maplibregl.Map.prototype.eachLayer = function(fn, context) {
            var self = this;
            this.style && this.style._layers && Object.keys(this.style._layers).forEach(function(id) {
                var layer = self.style._layers[id];
                if (layer) {
                    fn.call(context, {
                        _maplibreLayer: layer,
                        _layerId: id,
                        remove: function() {
                            if (self.getLayer && self.getLayer(id)) {
                                self.removeLayer(id);
                            }
                        }
                    });
                }
            });
            return this;
        };
        
        maplibregl.Map.prototype.hasLayer = function(layer) {
            if (typeof layer === 'string') {
                return !!(this.getLayer && this.getLayer(layer));
            } else if (layer && layer._layerId) {
                return !!(this.getLayer && this.getLayer(layer._layerId));
            }
            return false;
        };
        
        maplibregl.Map.prototype.removeLayer = function(layerOrId) {
            var id = typeof layerOrId === 'string' ? layerOrId : 
                     (layerOrId._layerId || layerOrId.id);
            if (this.getLayer && this.getLayer(id)) {
                this.removeLayer(id);
            }
            return this;
        };
        
        maplibregl.Map.prototype.addLayer = function(layer) {
            if (layer._maplibreLayer || layer.type) {
                // Layer already added or is a native MapLibre layer
            }
            return this;
        };
    }

    // ============================================================
    // UTIL - Utility functions (MUST be defined before L_Class)
    // ============================================================
    
    var L_Util = {
        extend: function(dest) {
            var sources = Array.prototype.slice.call(arguments, 1);
            for (var i = 0; i < sources.length; i++) {
                var src = sources[i];
                for (var key in src) {
                    if (src.hasOwnProperty(key)) {
                        dest[key] = src[key];
                    }
                }
            }
            return dest;
        },
        bind: function(func, context) {
            return function() {
                return func.apply(context, arguments);
            };
        },
        stamp: function(obj) {
            if (!obj._leaflet_id) {
                obj._leaflet_id = ++L_Util._idCounter;
            }
            return obj._leaflet_id;
        },
        falseFn: function() { return false; },
        requestAnimFrame: function(fn, context, immediate) {
            if (immediate) {
                fn.call(context);
            } else {
                setTimeout(function() { fn.call(context); }, 0);
            }
        },
        cancelAnimFrame: function(id) {
            clearTimeout(id);
        },
        _idCounter: 0,
        setOptions: function(obj, options) {
            if (!obj.options) obj.options = {};
            obj.options = L_Util.extend({}, obj.options, options);
            return obj;
        },
        template: function(str, data) {
            return str.replace(/\{ *([\w_]+) *\}/g, function(match, key) {
                var value = data[key];
                return value !== undefined ? value : '';
            });
        }
    };
    
    global.L_Util = L_Util;
    global.L.Util = L_Util;
    global.L.bind = L_Util.bind;
    global.L.setOptions = L_Util.setOptions;

    // ============================================================
    // CLASS SYSTEM - Fixed implementation without infinite recursion
    // ============================================================
    
    function L_Class() {
        // Base class constructor - no-op
    }

    // L_Class.include - adds properties to prototype
    L_Class.include = function(props) {
        L_Util.extend(this.prototype, props);
        return this;
    };

    // L_Class.extend - creates a new class that inherits from this class
    // Uses Object.create to avoid circular references
    L_Class.extend = function(props) {
        // Create the constructor for the new class
        function ExtendedClass() {
            // Call parent constructor if it exists
            if (this.initialize) {
                this.initialize.apply(this, arguments);
            }
        }
        
        // Inherit prototype from parent using Object.create (no circular reference)
        ExtendedClass.prototype = Object.create(this.prototype);
        ExtendedClass.prototype.constructor = ExtendedClass;
        
        // Add __super__ reference to parent prototype
        ExtendedClass.__super__ = this.prototype;
        
        // Copy static properties (extend method)
        ExtendedClass.extend = this.extend;
        
        // Copy own properties from props to the new prototype
        for (var key in props) {
            if (props.hasOwnProperty(key)) {
                ExtendedClass.prototype[key] = props[key];
            }
        }
        
        return ExtendedClass;
    };

    // Add to global L namespace
    global.L_Class = L_Class;
    global.L = global.L || {};
    global.L.Class = L_Class;
    global.L.extend = L_Class.extend;

    // ============================================================
    // EVENTED - Base class for event handling
    // ============================================================
    
    var L_Evented = L_Class.extend({
        initialize: function() {
            this._eventHandlers = {};
        },
        
        on: function(eventName, handler, context) {
            if (!this._eventHandlers) this._eventHandlers = {};
            if (!this._eventHandlers[eventName]) {
                this._eventHandlers[eventName] = [];
            }
            this._eventHandlers[eventName].push({
                handler: handler,
                context: context || this
            });
            return this;
        },
        
        off: function(eventName, handler, context) {
            if (!this._eventHandlers || !this._eventHandlers[eventName]) return this;
            
            if (!handler) {
                delete this._eventHandlers[eventName];
                return this;
            }
            
            var handlers = this._eventHandlers[eventName];
            for (var i = handlers.length - 1; i >= 0; i--) {
                if (handlers[i].handler === handler && 
                    (!context || handlers[i].context === context)) {
                    handlers.splice(i, 1);
                }
            }
            return this;
        },
        
        fire: function(eventName, data) {
            if (!this._eventHandlers || !this._eventHandlers[eventName]) return this;
            var handlers = this._eventHandlers[eventName];
            for (var i = 0; i < handlers.length; i++) {
                handlers[i].handler.call(handlers[i].context, data || {});
            }
            return this;
        },
        
        listens: function(eventName) {
            return !!(this._eventHandlers && this._eventHandlers[eventName]);
        }
    });

    global.L.Evented = L_Evented;

    // ============================================================
    // LAYER - Base layer class
    // ============================================================
    
    var L_Layer = L_Evented.extend({
        addTo: function(map) {
            if (map && map.addLayer) {
                map.addLayer(this);
            }
            return this;
        },
        
        remove: function() {
            if (this._map && this._map.removeLayer) {
                this._map.removeLayer(this);
            }
            return this;
        },
        
        removeFrom: function(map) {
            if (map && map.removeLayer) {
                map.removeLayer(this);
            }
            return this;
        },
        
        onAdd: function(map) {
            this._map = map;
        },
        
        onRemove: function(map) {
            delete this._map;
        }
    });
