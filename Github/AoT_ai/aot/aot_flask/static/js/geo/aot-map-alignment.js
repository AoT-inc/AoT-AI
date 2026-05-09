/**
 * aot-map-alignment.js
 * Global Label Collision Detection for multiple Map Widgets.
 * Implements a stable 'Strict Hide' logic: overlapping labels are hidden based on priority.
 * No shifting, no clustering, no virtual representatives - ensures maximum stability.
 */
window.AoTMapAlignment = (function () {
    const registry = {}; // mapId -> { map, groups: [], enabled: true }
    let _debounceTimer = null;
    let _alignmentPadding = 2; // Pixels of padding around labels

    /**
     * Initialize Alignment for a specific map instance
     */
    function init(mapId, mapInstance, options) {
        if (!mapId) return;

        registry[mapId] = {
            map: mapInstance,
            groups: [],
            enabled: options ? options.enabled : true,
            padding: (options && options.padding !== undefined) ? options.padding : 2 // Store per-map padding
        };

        // Bind map events for re-calculation
        // Support both Leaflet-style and MapLibre-style events
        if (mapInstance.on) {
            mapInstance.on('zoomend moveend layeradd layerremove', () => {
                if (registry[mapId] && registry[mapId].enabled) {
                    updateAlignment();
                }
            });
        }

        updateAlignment();
    }

    /**
     * Get proper coordinates from layer
     */
    function getLayerCoords(layer) {
        if (!layer || !layer.getElement) return null;

        const el = layer.getElement();
        if (!el) return null;

        // Check for marker-pill or aot-label-content child
        const mEl = el.querySelector('.aot-label-content') || el.querySelector('.marker-pill') || el;
        return mEl;
    }

    /**
     * Check if map container is visible
     */
    function isMapVisible(entry) {
        const container = entry.map && entry.map.getContainer ? entry.map.getContainer() : null;
        return container && container.offsetParent !== null;
    }

    /**
     * Register a Layer Group for collision monitoring
     * [Modified] Added isCluster flag to explicitly bypass collision for cluster groups
     */
    function registerGroup(mapId, type, layerGroup, priority, isCluster = false) {
        if (!mapId || !registry[mapId]) return;

        registry[mapId].groups = registry[mapId].groups.filter(g => g.type !== type);
        registry[mapId].groups.push({ type, layerGroup, priority, isCluster });
        registry[mapId].groups.sort((a, b) => a.priority - b.priority);
    }

    /**
     * Global update trigger with debounce
     */
    function updateAlignment() {
        if (_debounceTimer) clearTimeout(_debounceTimer);
        
        _debounceTimer = setTimeout(() => {
            requestAnimationFrame(() => {
                try {
                    _performGlobalCollisionCheck();
                } catch (e) {
                    console.error("[AoT Alignment] Check failed:", e);
                }
            });
        }, 150); // Stable debounce
    }

    /**
     * Strict Priority-based Collision Check (Simple Hide)
     * Updated to support both Leaflet and MapLibre map layers
     */
    function _performGlobalCollisionCheck() {
        const allLayersRaw = [];
        const placedRects = [];

        // 1. Collect all layers across all maps
        Object.keys(registry).forEach(mapId => {
            const entry = registry[mapId];
            if (!isMapVisible(entry)) return;

            if (!entry.enabled) {
                // If disabled, show everything and restore original transforms
                entry.groups.forEach(g => {
                    if (g.layerGroup && g.layerGroup.eachLayer) {
                        g.layerGroup.eachLayer(layer => {
                            const el = layer.getElement ? layer.getElement() : null;
                            if (el) {
                                el.style.display = 'block';
                                el.style.opacity = '1';
                                const mEl = el.querySelector('.aot-label-content') || el.querySelector('.marker-pill') || el.firstElementChild || el;
                                if (mEl) {
                                    mEl.style.transform = (el.dataset.originalTransform && el.dataset.originalTransform !== 'none') ? el.dataset.originalTransform : '';
                                }
                            }
                        });
                    }
                });
                return;
            }

            entry.groups.forEach(g => {
                // Skip if layerGroup is not iterable
                if (!g.layerGroup || !g.layerGroup.eachLayer) return;

                g.layerGroup.eachLayer(layer => {
                    // Support both Leaflet and MapLibre layer APIs
                    const el = (layer.getElement && layer.getElement()) || (layer._icon);

                    // If clustered or no element, skip
                    if (!el) return;
                    
                    // If it's a device in a cluster group, we SKIP collision hiding 
                    // because MarkerCluster already manages its visibility based on zoom.
                    // IMPORTANT: Spiderfied markers ARE visible and overlap, so specific bypass is needed.
                    if (g.isCluster) {
                        el.style.display = 'block';
                        el.style.opacity = '1';
                        return;
                    }

                    // Cache original transform if not already done
                    if (!el.dataset.originalTransform || el.dataset.originalTransform === 'none' || el.dataset.originalTransform.replace(/\s/g, '') === 'matrix(1,0,0,1,0,0)') {
                       const mEl = el.querySelector('.aot-label-content') || el.querySelector('.marker-pill') || el.firstElementChild || el;
                       let trans = window.getComputedStyle(mEl).transform;
                       
                       // [Fix] Fallback for labels that MUST be centered
                       // Check both child (mEl) and parent (el) for classes that indicate centering intent
                       const hasCenteringClass = (mEl && (mEl.classList.contains('marker-pill') || mEl.classList.contains('aot-label-content'))) || 
                                               (el && (el.classList.contains('geo-label-marker') || el.classList.contains('aot-map-text-marker')));
                       
                       if (hasCenteringClass) {
                           const isNoneOrZero = !trans || trans === 'none' || trans.replace(/\s/g, '') === 'matrix(1,0,0,1,0,0)';
                           if (isNoneOrZero) trans = 'translate(-50%, -50%)';
                       }
                       el.dataset.originalTransform = trans;
                    }

                    // Measurement Pass: Temporarily show with 0 opacity
                    el.style.display = 'block';
                    el.style.opacity = '0';
                    el.style.pointerEvents = 'none';

                    allLayersRaw.push({
                        layer, el, priority: g.priority, mapId,
                        name: layer.aot_name || (layer.feature && layer.feature.properties ? (layer.feature.properties.label_name || layer.feature.properties.name) : "") || "Unknown"
                    });
                });
            });
        });

        // 2. Sort by Priority (Group Priority ASC) -> zIndexOffset (DESC) -> Name (ASC)
        allLayersRaw.sort((a, b) => {
            // Primary: Group Priority (1=Device, 3=Site, 4=Zone) - Lower is better
            if (a.priority !== b.priority) return a.priority - b.priority;
            
            // Secondary: zIndexOffset (Visual Stack) - Higher is better
            // Output(10000) > Input(5000) > Site(1000)
            const zA = (a.layer.options && a.layer.options.zIndexOffset) ? a.layer.options.zIndexOffset : 0;
            const zB = (b.layer.options && b.layer.options.zIndexOffset) ? b.layer.options.zIndexOffset : 0;
            if (zA !== zB) return zB - zA; // Descending

            // Tertiary: Name Alphabetical
            return String(a.name).localeCompare(String(b.name));
        });

        // 3. Collision Logic (AABB)
        allLayersRaw.forEach(item => {
            const mEl = item.el.querySelector('.aot-label-content') || item.el.querySelector('.marker-pill') || item.el.firstElementChild || item.el;
            const originalTrans = (item.el.dataset.originalTransform && item.el.dataset.originalTransform !== 'none') ? item.el.dataset.originalTransform : '';
            
            // [Fix] Ghost Label Prevention: Skip if name is invalid
            if (!item.name || item.name === 'undefined' || item.name.trim() === '') {
                item.el.style.display = 'none';
                return;
            }

            // Apply original transform for accurate measurement
            mEl.style.transform = originalTrans;
            void mEl.offsetWidth; // Force reflow
            const rect = mEl.getBoundingClientRect();

            if (rect.width <= 1) {
                // Not visible or not rendered yet
                item.el.style.display = 'none';
                return;
            }
            
            // [Fix] Retrieve padding for this specific map
            const currentMapPadding = (registry[item.mapId] && registry[item.mapId].padding !== undefined) ? registry[item.mapId].padding : 2;

            // Check if this label overlaps with any already placed labels
            let isOverlapping = false;
            for (let r of placedRects) {
                const overlap = !(
                    rect.right + currentMapPadding < r.left ||
                    rect.left - currentMapPadding > r.right ||
                    rect.bottom + currentMapPadding < r.top ||
                    rect.top - currentMapPadding > r.bottom
                );
                if (overlap) {
                    isOverlapping = true;
                    break;
                }
            }

            if (isOverlapping) {
                item.el.style.display = 'none';
            } else {
                item.el.style.display = 'block';
                item.el.style.opacity = '1';
                item.el.style.pointerEvents = 'auto';
                placedRects.push(rect);
            }
        });
    }

    return {
        init,
        registerGroup,
        updateAlignment,
        _debugRegistry: registry,
        clearExpansion: () => {} // Legacy no-op
    };

})();
