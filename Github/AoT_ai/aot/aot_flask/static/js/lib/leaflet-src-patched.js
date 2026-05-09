/**
 * AoT Leaflet Class.js Patched Version
 * 
 * This file patches the callInitHooks issue in Leaflet's Class system.
 * 
 * PROBLEM: In Leaflet's original Class.js, the constructor K calls 
 * this.callInitHooks() but callInitHooks is only defined on proto AFTER K.
 * This causes "this.callInitHooks is not a function" error.
 * 
 * SOLUTION: Define callInitHooks on proto BEFORE defining K, and ensure
 * K's prototype is set to the already-patched proto.
 */

(function(global) {
    'use strict';
    
    console.log('[AoT] Loading patched Class.js...');
    
    // Store original NewClass if it exists
    var OriginalNewClass = global.NewClass;
    var OriginalClass = global.L ? global.L.Class : null;
    
    // ============================================================
    // PATCHED NewClass - callInitHooks is defined BEFORE constructor
    // ============================================================
    var PatchedNewClass = function(parent, props) {
        var proto, K, k;
        
        // Create base prototype - this works even if parent is undefined
        var F = function() {};
        F.prototype = parent ? parent.prototype : {};
        
        // AoT FIX: Define callInitHooks on proto FIRST, before K
        proto = new F();
        
        // AoT FIX: Ensure callInitHooks exists on proto
        if (!proto.callInitHooks) {
            proto.callInitHooks = function() {
                if (this._initHooks && this._initHooks.length) {
                    for (var i = 0; i < this._initHooks.length; i++) {
                        if (typeof this._initHooks[i] === 'function') {
                            this._initHooks[i].call(this);
                        }
                    }
                }
            };
        }
        
        // AoT FIX: Ensure _initHooks array exists
        if (!proto._initHooks) {
            proto._initHooks = [];
        }
        
        // AoT FIX: Add addInitHook to proto
        if (!proto.addInitHook) {
            proto.addInitHook = function(fn) {
                var args = Array.prototype.slice.call(arguments, 1);
                var init = typeof fn === 'function' ? fn : function() {
                    this[fn].apply(this, args);
                };
                this._initHooks = this._initHooks || [];
                this._initHooks.push(init);
            };
        }
        
        // ============================================================
        // Constructor K - NOW callInitHooks IS AVAILABLE
        // ============================================================
        K = function() {
            // AoT FIX: Initialize _initHooks FIRST
            this._initHooks = this._initHooks || [];
            
            // Call parent constructor if exists
            if (parent) {
                parent.apply(this, arguments);
            }
            
            // AoT FIX: callInitHooks is NOW DEFINED on proto, so this.callInitHooks works!
            this.callInitHooks();
        };
        
        // Set K's prototype to our already-patched proto
        K.prototype = proto;
        
        // Add extend method
        K.extend = function(props) {
            return PatchedNewClass(this, props);
        };
        
        // Add addInitHook as static method
        K.addInitHook = function(fn) {
            var args = Array.prototype.slice.call(arguments, 1);
            var init = typeof fn === 'function' ? fn : function() {
                this[fn].apply(this, args);
            };
            this.prototype._initHooks = this.prototype._initHooks || [];
            this.prototype._initHooks.push(init);
        };
        
        // Apply any additional props
        if (props) {
            for (var prop in props) {
                if (props.hasOwnProperty(prop) && prop !== 'prototype') {
                    K[prop] = props[prop];
                }
            }
            // Copy props to prototype for methods
            if (props.prototype) {
                for (var p in props.prototype) {
                    if (props.prototype.hasOwnProperty(p)) {
                        proto[p] = props.prototype[p];
                    }
                }
            }
        }
        
        return K;
    };
    
    // ============================================================
    // L.Class = patched version
    // ============================================================
    if (typeof global.L !== 'undefined') {
        global.L.Class = PatchedNewClass();
        global.L.Class.extend = function(props) {
            return PatchedNewClass(this, props);
        };
        global.L.Class.addInitHook = function(fn) {
            var args = Array.prototype.slice.call(arguments, 1);
            var init = typeof fn === 'function' ? fn : function() {
                this[fn].apply(this, args);
            };
            this.prototype._initHooks = this.prototype._initHooks || [];
            this.prototype._initHooks.push(init);
        };
        
        // Also set as NewClass for compatibility
        global.L.NewClass = PatchedNewClass;
        
        console.log('[AoT] L.Class and L.NewClass patched successfully');
    } else {
        // Create minimal L object if it doesn't exist
        global.L = {
            Class: PatchedNewClass(),
            NewClass: PatchedNewClass
        };
        global.L.Class.extend = function(props) {
            return PatchedNewClass(this, props);
        };
        
        console.log('[AoT] Created L.Class and L.NewClass');
    }
    
    // Also set global NewClass
    global.NewClass = PatchedNewClass;
    
    console.log('[AoT] Class.js patched successfully - callInitHooks is now available in constructors');
    
})(typeof window !== 'undefined' ? window : this);
