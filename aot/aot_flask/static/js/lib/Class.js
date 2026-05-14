/**
 * AoT Class.js Polyfill
 * Patches CDN Leaflet's Class.js to fix callInitHooks implementation
 * 
 * Load AFTER Leaflet CDN to patch the bug where this.callInitHooks is not a function
 */

(function() {
    'use strict';
    
    console.log('[AoT Polyfill] Class.js polyfill loading...');
    
    function execInitHooks(obj) {
        if (obj._initHooks && obj._initHooks.length) {
            for (var i = 0; i < obj._initHooks.length; i++) {
                if (typeof obj._initHooks[i] === 'function') {
                    obj._initHooks[i].call(obj);
                }
            }
        }
    }
    
    // Patch L.NewClass.prototype.callInitHooks
    if (typeof window.L !== 'undefined' && window.L.NewClass) {
        if (!L.NewClass.prototype.callInitHooks) {
            L.NewClass.prototype.callInitHooks = function() {
                execInitHooks(this);
            };
            console.log('[AoT Polyfill] L.NewClass.prototype.callInitHooks patched');
        }
        if (!L.NewClass.prototype._initHooks) {
            L.NewClass.prototype._initHooks = [];
        }
    }
    
    // Patch L.Class.prototype.callInitHooks
    if (typeof window.L !== 'undefined' && window.L.Class) {
        if (!L.Class.prototype.callInitHooks) {
            L.Class.prototype.callInitHooks = function() {
                execInitHooks(this);
            };
            console.log('[AoT Polyfill] L.Class.prototype.callInitHooks patched');
        }
        if (!L.Class.prototype._initHooks) {
            L.Class.prototype._initHooks = [];
        }
    }
    
    // Patch window.NewClass as fallback
    if (typeof window.NewClass !== 'undefined') {
        if (!window.NewClass.prototype.callInitHooks) {
            window.NewClass.prototype.callInitHooks = function() {
                execInitHooks(this);
            };
            console.log('[AoT Polyfill] window.NewClass.prototype.callInitHooks patched');
        }
        if (!window.NewClass.prototype._initHooks) {
            window.NewClass.prototype._initHooks = [];
        }
    }
    
    console.log('[AoT Polyfill] Class.js polyfill loaded successfully');
})();
