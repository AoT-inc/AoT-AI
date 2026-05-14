/**
 * AoT Geo View Logic (Read-Only)
 * For Main Map Monitoring Screen
 * [MapLibre Migration] Updated for MapLibre GL compatibility
 */

class AoTGeoView {
    constructor(mapId) {
        this.mapId = mapId;
        this.map = null;
        this.currentMapUuid = null;

        // Layers - Use AoTGeoLayerGroup for MapLibre compatibility
        this.featureGroup = null;

        this.apiBase = '/api/geo';
    }

    init(mapConfigs) {
        // console.log("AoTGeoView initializing...");
        this.mapConfigs = mapConfigs || [];

        // Initialize feature group for layer storage
        if (typeof AoTGeoLayerGroup !== 'undefined') {
            this.featureGroup = new AoTGeoLayerGroup('view_features');
        }

        // 1. Initialize Map via Standard Loader
        // This handles Global Config, Base Layers, and Attribution correctly.
        if (window.AoTMapLoader) {
            const initResult = window.AoTMapLoader.initMap(this.mapId, 'general_map');
            this.map = initResult.map;

            // Optional: Store loader references if needed later
            // this.layerControl = initResult.layerControl;
        } else if (window.AoTMapLibreLoader) {
            // [MapLibre] Use pure MapLibre loader
            this.map = window.AoTMapLibreLoader.initMap(this.mapId, 'general_map');
        } else {
            // Fallback: MapLibre only (Leaflet removed for MapLibre migration)
            if (typeof maplibregl !== 'undefined') {
                this.map = new maplibregl.Map({
                    container: this.mapId,
                    center: [126.9780, 37.5665],
                    zoom: 13
                });
                this.map.addControl(new maplibregl.NavigationControl(), 'top-right');
            }
        }

        // 3. Add Feature Group to map
        if (this.featureGroup) {
            this.featureGroup.addTo(this.map);
            if (this.featureGroup.on) {
                this.featureGroup.on('click', (e) => this._onFeatureClick(e));
            }
        }

        // 4. Load Initial Map (Most recent)
        if (this.mapConfigs.length > 0) {
            this.loadMap(this.mapConfigs[0].unique_id);
        } else {
            // console.warn("No maps available to load.");
        }
    }

    loadMap(uuid) {
        // console.log("Loading Map View:", uuid);
        this.currentMapUuid = uuid;
        if (this.featureGroup && this.featureGroup.clearLayers) {
            this.featureGroup.clearLayers();
        }

        // Update UI Selector if needed directly?
        // User might have selected from dropdown, so it's already updated.
        // But if auto-loaded:
        const selector = document.getElementById('map-selector');
        if (selector && selector.value !== uuid) {
            selector.value = uuid;
        }

        // Fetch Overlays
        fetch(`${this.apiBase}/overlays?map_uuid=${uuid}`)
            .then(res => res.json())
            .then(data => {
                if (data.features && Array.isArray(data.features)) {
                    // [MapLibre] Use AoTGeoLayer.fromGeoJSON or L.geoJSON depending on what's available
                    let layers = [];
                    if (typeof AoTGeoLayer !== 'undefined') {
                        layers = AoTGeoLayer.fromGeoJSON(data, {
                            onEachFeature: (feature, layer) => {
                                this._styleLayer(layer);
                                this._bindPopup(layer);
                                if (this.featureGroup) {
                                    this.featureGroup.addLayer(layer);
                                }
                            }
                        });
                    }

                    // Populate Sidebar Tree
                    this._buildSidebarTree();

                    // Fit Bounds
                    if (this.featureGroup && this.featureGroup.getLayers && this.featureGroup.getLayers().length > 0) {
                        const bounds = this.featureGroup.getBounds();
                        if (bounds && bounds.isValid && bounds.isValid()) {
                            this.map.fitBounds(bounds);
                        }
                    }
                }
            })
            .catch(err => {
                // console.error("Failed to load overlays:", err);
            });
    }

    _styleLayer(layer) {
        const props = layer.feature.properties || {};
        const level = props.level_id || 1;

        if (level === 1) { // Site
            if (layer.setStyle) layer.setStyle({ color: '#ffcc00', weight: 3, fillOpacity: 0.1 });
        } else if (level === 2) { // Zone
            if (layer.setStyle) layer.setStyle({ color: '#00aa00', weight: 2, fillOpacity: 0.2, dashArray: '5,5' });
        }
    }

    _bindPopup(layer) {
        const props = layer.feature.properties || {};
        let content = `<b>${props.name || 'Unnamed'}</b>`;
        if (props.level_id === 3) {
            content += `<br>Device ID: ${props.device_id || 'N/A'}`;
        }
        layer.bindPopup(content);
    }

    _onFeatureClick(e) {
        // Handle clicks on map features (zoom to, select in sidebar)
        const layer = e.layer;
        // console.log("Clicked:", layer.feature.properties.name);
    }

    _buildSidebarTree() {
        // Organize features by hierarchy: Site -> Zone -> Device
        const treeRoot = document.getElementById('geo-tree-root');
        if (!treeRoot) return;
        treeRoot.innerHTML = ''; // Clear

        const features = [];
        this.featureGroup.eachLayer(l => features.push(l.feature));

        // Simple hierarchy builder
        const sites = features.filter(f => f.properties.level_id === 1);
        const zones = features.filter(f => f.properties.level_id === 2);
        const devices = features.filter(f => f.properties.level_id === 3);

        if (sites.length === 0 && features.length > 0) {
            // Handle loose items?
        }

        sites.forEach(site => {
            const li = document.createElement('li');
            li.className = 'list-group-item p-2';
            li.innerHTML = `<div><i class="fas fa-vector-square text-warning mr-2"></i><b>${site.properties.name || 'Site'}</b></div>`;
            li.style.cursor = 'pointer';
            li.onclick = () => this._flyToFeature(site);

            // Allow click to zoom

            // Find children zones
            // Assuming geometric containment or strict ID linkage? 
            // Current DB model uses parent_id. 
            // But Overlays API might not return full hierarchy info cleanly?
            // Actually `api/geo.py` returns basic properties.
            // If parent_id is in properties, we can link them.
            // Assuming simple list for now.

            treeRoot.appendChild(li);
        });

        // If no sites, just list everything?
        if (sites.length === 0) {
            features.forEach(f => {
                const li = document.createElement('li');
                li.className = 'list-group-item p-2';
                li.innerText = f.properties.name || 'Feature';
                li.onclick = () => this._flyToFeature(f);
                treeRoot.appendChild(li);
            });
        }
    }

    _flyToFeature(feature) {
        // Find layer
        let targetLayer = null;
        this.featureGroup.eachLayer(l => {
            if (l.feature === feature) targetLayer = l;
        });

        if (targetLayer) {
            if (targetLayer.getBounds) {
                this.map.flyToBounds(targetLayer.getBounds(), { padding: [50, 50] });
            } else if (targetLayer.getLatLng) {
                this.map.flyTo(targetLayer.getLatLng(), 16);
            }
            targetLayer.openPopup();
        }
    }
}
