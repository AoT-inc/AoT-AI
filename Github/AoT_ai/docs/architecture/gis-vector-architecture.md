# GIS 벡터 전환 아키텍처 설계 문서

**문서 버전**: 1.0  
**작성일**: 2026-04-22  
**브랜치**: gis-vector (생성 예정)  
**상태**: 초안 (Draft)

---

## 목차

1. [개요](#1-개요)
2. [현재 시스템 분석](#2-현재-시스템-분석)
3. [벡터 전환 대상 파일 목록](#3-벡터-전환-대상-파일-목록)
4. [MapLibre-GL 벡터 전환 설계](#4-maplibre-gl-벡터-전환-설계)
5. [브릿지 레이어 구조](#5-브릿지-레이어-구조)
6. [그리기 도구 마이그레이션](#6-그리기-도구-마이그레이션)
7. [다중 지도 서비스 연동 아키텍처](#7-다중-지도-서비스-연동-아키텍처)
8. [마이그레이션 로드맵](#8-마이그레이션-로드맵)
9. [참고 문서](#9-참고-문서)

---

## 1. 개요

### 1.1 목적

본 문서는 AoT(Agriculture of Things) 시스템의 GIS 모듈을 Leaflet 기반 래스터 타일에서 MapLibre-GL 기반 벡터 타일로 전환하기 위한 아키텍처 설계를 기술한다.

### 1.2 배경

**참고 문서 IDs** (DB 문서):
- `83810ae7` — GIS 벡터 타일 전환 개요 및 영향 분석
- `6a20936d` — 벡터 엔진 비교 분석 및 권장 사항  
- `37a57732` — 다중 지도 서비스 연동 아키텍처
- `b8e7a52c` — 그리기 도구 벡터 전환 가이드

> ⚠️ **참고**: 위 문서들은 DB에서 조회해야 하며, 본 설계는 현재 코드베이스 분석을 기반으로 작성됨.

### 1.3 목표

1. **성능 향상**: 벡터 타일의 작은 페이로드와 스타일 렌더링으로 로딩 속도 개선
2. **시각적 일관성**: 다양한 지도 서비스 간 스타일 커스터마이징
3. **확장성**: 다중 지도 소시(Layer) 동시 표시 지원
4. **호환성 유지**: 기존 Leaflet 기반 기능(마커, 팝업, WMS 오버레이) 보존

---

## 2. 현재 시스템 분석

### 2.1 기술 스택

| 구성요소 | 현재 기술 | 전환 목표 |
|---------|---------|---------|
| 지도 엔진 | Leaflet | MapLibre-GL |
| 타일 유형 | Raster (PNG/JPEG) | Vector (MVT/PBF) |
| 그리기 도구 | Leaflet.Draw | MapLibre-Geoman 또는 maplibre-gl-terradraw |
| 마커/팝업 | Leaflet API | MapLibre 마커 + 커스텀 HTML |
| WMS 오버레이 | Leaflet.WMS 플러그인 | 별도 래스터 레이어로 관리 |

### 2.2 현재 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (Browser)                      │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ aot-map-    │  │ aot-map-    │  │ aot-map-          │  │
│  │ loader.js   │  │ editor-v2.js│  │ custom-controls.js│  │
│  └─────────────┘  └──────────────┘  └───────────────────┘  │
│         │                │                    │             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Leaflet Map (L.Map)                      │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────────┐  │  │
│  │  │ L.TileLayer│  │ L.Marker  │  │ L.FeatureGroup │  │  │
│  │  │ (WMTS/XYZ)│  │           │  │ (Shapes/Draw)  │  │  │
│  │  └────────────┘  └────────────┘  └────────────────┘  │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                      Backend (Flask)                          │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ aot/inputs_  │  │ aot/aot_     │  │ API Endpoints    │  │
│  │ gis/         │  │ flask/routes │  │ /api/maps_*      │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 현재 GIS 프로바이더 (aot/inputs_gis/)

| 파일명 | 유형 | 설명 |
|-------|------|------|
| `base_input_gis.py` | 추상 클래스 | GIS 프로바이더 베이스 클래스 |
| `gis_vworld.py` | WMTS/WMS | 한국국토정보원 벡터/위성지도 |
| `gis_maptiler_vector.py` | Vector | MapTiler 벡터 타일 (이미 벡터 지원) |
| `gis_osm.py` | XYZ | OpenStreetMap |
| `gis_google.py` | XYZ | Google Maps |
| `gis_naver.py` | XYZ | Naver 지도 |
| `gis_kakao.py` | XYZ | 카카오맵 |
| `gis_mapbox.py` | XYZ | Mapbox |
| `gis_esri.py` | XYZ/WMS | Esri World Imagery |
| `gis_bing.py` | QuadKey | Bing Maps |
| `gis_sgis.py` | WMS | 통계청 SGIS |
| `gis_nasa_gibs.py` | WMTS | NASA GIBS 위성이미지 |
| `gis_openweather.py` | XYZ | 날씨 오버레이 |
| `gis_rainviewer.py` | XYZ | 레이더 오버레이 |

### 2.4 현재 프론트엔드 JS 모듈

| 파일명 | 크기 | 역할 |
|-------|------|------|
| `aot-map-loader.js` | 41KB | 지도 초기화, 레이어 로딩 |
| `aot-map-editor.js` | 14KB | Leaflet.Draw 기반 그리기 |
| `aot-map-editor-v2.js` | 14KB | 그리기 도구 v2 |
| `aot-map-utils.js` | 33KB | 지오메트리 유틸리티 (Turf.js) |
| `aot-map-controls.js` | 17KB | 줌/도구 컨트롤 |
| `aot-map-custom-controls.js` | 49KB | 커스텀 컨트롤 (SiteList, Measure) |
| `aot-map-config.js` | 12KB | 설정 관리 |
| `aot-map-data.js` | 15KB | 데이터 페치/업데이트 |
| `aot-map-modal.js` | 26KB | 모달/팝업 관리 |
| `aot-map-alignment.js` | 9KB | 정렬 기능 |
| `aot-geo-design-v3.js` | 124KB | Geo Design 메인 번들 |
| `aot-geo-panel.js` | 56KB | 패널 UI |
| `aot-geo-settings.js` | 18KB | 설정 패널 |
| `aot-geo-view.js` | 6KB | 뷰 관리 |
| `aot-geo-input-preview.js` | 25KB | 입력 미리보기 |

### 2.5 기존 벡터 타일 지원

**이미 존재하는 파일**: `aot/aot_flask/static/js/map/aot-vector-tile-loader.js`

```javascript
// 기존 MapLibre-GL 래퍼 구조
var VectorTileLayer = L.Layer.extend({
    options: {
        styleUrl: '',
        apiKey: '',
        language: 'auto',
        maxZoom: 22,
        maxNativeZoom: 14
    },
    _initMapLibre: function() {
        this._glMap = new maplibregl.Map({
            container: this._container,
            style: this.options.styleUrl,
            crs: L.CRS.EPSG3857,
            interactive: false
        });
    }
});
```

---

## 3. 벡터 전환 대상 파일 목록

### 3.1 백엔드 (aot/inputs_gis/)

| 파일 | 전환 필요성 | 우선순위 | 비고 |
|-----|-----------|---------|------|
| `base_input_gis.py` | 있음 | P1 | 레이어 타입에 vector 추가 |
| `gis_maptiler_vector.py` | 없음 | - | 이미 벡터 지원 |
| `gis_vworld.py` | 있음 | P2 | WMTS → 벡터 전환 고려 |
| `gis_osm.py` | 있음 | P2 | OSM 벡터 전환 |
| `gis_mapbox.py` | 있음 | P2 | Mapbox 벡터 |

### 3.2 프론트엔드 (aot/aot_flask/static/js/geo/)

| 파일 | 전환 필요성 | 우선순위 | 비고 |
|-----|-----------|---------|------|
| `aot-map-loader.js` | **높음** | P1 | 메인 전환 대상 |
| `aot-map-editor.js` | **높음** | P1 | 그리기 도구 교체 |
| `aot-map-editor-v2.js` | **높음** | P1 | 그리기 도구 교체 |
| `aot-map-utils.js` | 보통 | P2 | 좌표계 호환 확인 |
| `aot-map-controls.js` | 보통 | P2 | MapLibre 컨트롤로 마이그레이션 |
| `aot-map-custom-controls.js` | 보통 | P2 | 커스텀 컨트롤 재구현 |
| `aot-map-modal.js` | 낮음 | P3 | 팝업 호환 가능 |
| `aot-map-data.js` | 낮음 | P3 | API 연동 유지 |

### 3.3 새 파일 추가 필요

| 파일 | 역할 |
|-----|------|
| `aot-maplibre-core.js` | MapLibre-GL 맵 초기화 모듈 |
| `aot-vector-layer-manager.js` | 벡터 레이어 관리자 |
| `aot-maplibre-draw.js` | MapLibre-Geoman 통합 |
| `aot-raster-bridge.js` | Leaflet ↔ MapLibre 브릿지 |
| `aot-popup-manager.js` | MapLibre 팝업 관리 |

---

## 4. MapLibre-GL 벡터 전환 설계

### 4.1 전환 전략

**선택된 전략**: Hybrid Migration (점진적 전환)
- Phase 1: MapLibre-GL을 Leaflet 플러그인으로 통합 (기존 Leaflet 유지)
- Phase 2: 점진적으로 핵심 기능을 MapLibre로 이전
- Phase 3: Leaflet 완전 제거

### 4.2 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────────────┐
│                         Browser                                  │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    MapLibre-GL Container                  │   │
│  │  ┌────────────────────────────────────────────────────┐  │   │
│  │  │            Vector Tile Layer (MVT)                 │  │   │
│  │  │  - Base Map (MapTiler/OSM/Mapbox)                 │  │   │
│  │  │  - Labels & POI                                    │  │   │
│  │  └────────────────────────────────────────────────────┘  │   │
│  │  ┌────────────────────────────────────────────────────┐  │   │
│  │  │           AoT Custom Layers (GeoJSON)              │  │   │
│  │  │  - Device Markers                                  │  │   │
│  │  │  - Facility Boundaries                             │  │   │
│  │  │  - Drawn Shapes                                    │  │   │
│  │  └────────────────────────────────────────────────────┘  │   │
│  │  ┌────────────────────────────────────────────────────┐  │   │
│  │  │         Leaflet Raster Overlay (Bridge)            │  │   │
│  │  │  - WMS Layers                                     │  │   │
│  │  │  - Legacy Raster Tiles                            │  │   │
│  │  └────────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Common UI Layer                         │   │
│  │  - Popups (HTML Overlay)                                 │   │
│  │  - Controls (Zoom, Fullscreen)                           │   │
│  │  - Search Overlay                                        │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 4.3 핵심 모듈 설계

#### 4.3.1 MapLibre Core (`aot-maplibre-core.js`)

```javascript
/**
 * AoTMapLibre - MapLibre-GL 기반 지도 코어
 * Leaflet과의 호환성을 유지하면서 MapLibre 기능 활용
 */
class AoTMapLibre {
    constructor(containerId, options = {}) {
        this.containerId = containerId;
        this.defaultOptions = {
            center: [37.5665, 126.9780], // Seoul
            zoom: 12,
            maxZoom: 22,
            minZoom: 6,
            style: 'https://api.maptiler.com/styles/streets/style.json',
            language: 'auto'
        };
        this.options = { ...this.defaultOptions, ...options };
        this.map = null;
        this.markers = new Map();
        this.popups = new Map();
        this.customLayers = [];
    }

    init() {
        // CSS 로드
        this._ensureStyles();
        
        // MapLibre 초기화
        this.map = new maplibregl.Map({
            container: this.containerId,
            style: this.options.style,
            center: this.options.center,
            zoom: this.options.zoom,
            maxZoom: this.options.maxZoom,
            minZoom: this.options.minZoom,
            attributionControl: false
        });

        // 기본 컨트롤 추가
        this._initControls();
        
        // 이벤트 바인딩
        this._bindEvents();
        
        return this;
    }

    _ensureStyles() {
        if (document.querySelector('link[href*="maplibre-gl"]')) return;
        const css = document.createElement('link');
        css.rel = 'stylesheet';
        css.href = 'https://unpkg.com/maplibre-gl@4.1.1/dist/maplibre-gl.css';
        document.head.appendChild(css);
    }

    _initControls() {
        // 네비게이션 컨트롤
        this.map.addControl(
            new maplibregl.NavigationControl(),
            'top-left'
        );
        
        // 스케일바
        this.map.addControl(
            new maplibregl.ScaleControl(),
            'bottom-left'
        );
    }

    // 마커 관리
    addMarker(id, lngLat, options = {}) {
        const el = options.element || this._createDefaultMarker(options);
        
        const marker = new maplibregl.Marker({ element: el })
            .setLngLat(lngLat)
            .addTo(this.map);
        
        this.markers.set(id, marker);
        return marker;
    }

    removeMarker(id) {
        const marker = this.markers.get(id);
        if (marker) {
            marker.remove();
            this.markers.delete(id);
        }
    }

    // 팝업 관리
    addPopup(id, lngLat, content, options = {}) {
        const popup = new maplibregl.Popup({
            closeButton: true,
            closeOnClick: false,
            maxWidth: options.maxWidth || '300px'
        })
            .setLngLat(lngLat)
            .setHTML(content)
            .addTo(this.map);
        
        this.popups.set(id, popup);
        return popup;
    }

    // GeoJSON 레이어 추가
    addGeoJSONLayer(id, data, options = {}) {
        const layerConfig = {
            id: id,
            type: 'symbol', // 또는 'fill', 'line', 'circle'
            source: {
                type: 'geojson',
                data: data
            },
            layout: options.layout || {},
            paint: options.paint || {}
        };
        
        this.map.addLayer(layerConfig);
        this.customLayers.push(id);
        return this;
    }

    // WMS 래스터 레이어 (Leaflet 브릿지)
    addRasterOverlay(url, options = {}) {
        // Leaflet.Layer를 MapLibre에 통합
        const overlay = L.tileLayer.wms(url, {
            layers: options.layers,
            format: 'image/png',
            transparent: true,
            opacity: options.opacity || 0.7
        });
        
        // MapLibre 컨테이너 위에 Leaflet 레이어 추가
        overlay.addTo(this._leafletBridge);
        return this;
    }

    // 뷰 상태 동기화
    getView() {
        const center = this.map.getCenter();
        return {
            center: [center.lng, center.lat],
            zoom: this.map.getZoom(),
            bearing: this.map.getBearing(),
            pitch: this.map.getPitch()
        };
    }

    setView(view) {
        this.map.jumpTo({
            center: view.center,
            zoom: view.zoom,
            bearing: view.bearing || 0,
            pitch: view.pitch || 0
        });
    }

    // 레이어 가시성
    setLayerVisibility(layerId, visible) {
        this.map.setLayoutProperty(layerId, 'visibility', visible ? 'visible' : 'none');
    }

    // 리소스 정리
    destroy() {
        this.markers.forEach(m => m.remove());
        this.popups.forEach(p => p.remove());
        this.customLayers.forEach(id => {
            if (this.map.getLayer(id)) this.map.removeLayer(id);
            if (this.map.getSource(id)) this.map.removeSource(id);
        });
        if (this.map) this.map.remove();
    }
}

// 전역 네임스페이스 등록
window.AoTMapLibre = AoTMapLibre;
```

#### 4.3.2 벡터 레이어 관리자 (`aot-vector-layer-manager.js`)

```javascript
/**
 * AoT Vector Layer Manager
 * 다중 벡터 소스와 스타일 관리
 */
class AoTVectorLayerManager {
    constructor(map) {
        this.map = map;
        this.sources = new Map();
        this.styles = this._loadDefaultStyles();
    }

    _loadDefaultStyles() {
        return {
            device: {
                type: 'symbol',
                layout: {
                    'icon-image': 'marker-icon',
                    'icon-size': 1.2,
                    'text-field': ['get', 'name'],
                    'text-font': ['Noto Sans Regular'],
                    'text-offset': [0, 1.5],
                    'text-anchor': 'top'
                },
                paint: {
                    'text-color': '#333',
                    'text-halo-color': '#fff',
                    'text-halo-width': 2
                }
            },
            facility: {
                type: 'fill',
                paint: {
                    'fill-color': '#82898f',
                    'fill-opacity': 0.2
                }
            },
            zone: {
                type: 'line',
                paint: {
                    'line-color': '#28a745',
                    'line-width': 2,
                    'line-dasharray': [2, 2]
                }
            },
            site: {
                type: 'line',
                paint: {
                    'line-color': '#DF5353',
                    'line-width': 4
                }
            }
        };
    }

    // 벡터 타일 소스 추가
    addVectorSource(id, options) {
        const source = {
            type: 'vector',
            tiles: options.tiles, // ['https://.../{z}/{x}/{y}.pbf']
            minzoom: options.minzoom || 0,
            maxzoom: options.maxzoom || 14
        };
        
        this.map.addSource(id, source);
        this.sources.set(id, source);
        return this;
    }

    // GeoJSON 소스 추가
    addGeoJSONSource(id, data) {
        this.map.addSource(id, {
            type: 'geojson',
            data: data
        });
        return this;
    }

    // 스타일 기반 레이어 추가
    addStyledLayer(sourceId, layerId, styleType, paint = {}, layout = {}) {
        const layerConfig = {
            id: layerId,
            source: sourceId,
            ...this.styles[styleType],
            paint: { ...this.styles[styleType]?.paint, ...paint },
            layout: { ...this.styles[styleType]?.layout, ...layout }
        };
        
        this.map.addLayer(layerConfig);
        return this;
    }

    // 레이어 클릭 이벤트
    onLayerClick(layerIds, callback) {
        layerIds.forEach(id => {
            this.map.on('click', id, (e) => {
                callback(e.features, e.lngLat);
            });
            
            // 커서 스타일 변경
            this.map.on('mouseenter', id, () => {
                this.map.getCanvas().style.cursor = 'pointer';
            });
            this.map.on('mouseleave', id, () => {
                this.map.getCanvas().style.cursor = '';
            });
        });
    }

    // 레이어 필터
    setFilter(layerId, filter) {
        if (this.map.getLayer(layerId)) {
            this.map.setFilter(layerId, filter);
        }
    }
}
```

---

## 5. 브릿지 레이어 구조

### 5.1 목적

기존 Leaflet 기반 WMS 오버레이와 커스텀 래스터 레이어를 MapLibre 환경에서 계속 사용할 수 있도록 브릿지 레이어를 제공한다.

### 5.2 Leaflet ↔ MapLibre 브릿지

```javascript
/**
 * Leaflet-MapLibre Bridge Layer
 * MapLibre 위에 Leaflet 레이어를 투명한 컨테이너로 표시
 */
class AoTLeafletBridge {
    constructor(maplibreContainer, options = {}) {
        this.container = document.createElement('div');
        this.container.className = 'aot-leaflet-bridge';
        this.container.style.cssText = `
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: ${options.zIndex || 400};
        `;
        
        this.pointerContainer = document.createElement('div');
        this.pointerContainer.style.cssText = `
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: auto;
        `;
        
        this.container.appendChild(this.pointerContainer);
        maplibreContainer.appendChild(this.container);
        
        // Leaflet 지도 초기화
        this.leafletMap = L.map(this.pointerContainer, {
            zoomControl: false,
            attributionControl: false,
            dragging: false,
            scrollWheelZoom: false,
            doubleClickZoom: false,
            touchZoom: false
        });
        
        this.layers = [];
    }

    // Leaflet 레이어 추가
    addLayer(leafletLayer) {
        leafletLayer.addTo(this.leafletMap);
        this.layers.push(leafletLayer);
        return this;
    }

    // 뷰 동기화
    syncView(center, zoom) {
        this.leafletMap.setView(center, zoom, { animate: false });
    }

    // 크기 업데이트
    invalidateSize() {
        this.leafletMap.invalidateSize();
    }

    // 레이어 제거
    removeLayer(leafletLayer) {
        leafletLayer.remove();
        this.layers = this.layers.filter(l => l !== leafletLayer);
    }

    // 리소스 정리
    destroy() {
        this.layers.forEach(l => l.remove());
        this.leafletMap.remove();
        this.container.remove();
    }
}
```

### 5.3 WMS 오버레이 통합

```javascript
/**
 * WMS Overlay Manager for MapLibre
 */
class AoTWMSOverlayManager {
    constructor(maplibre, bridge) {
        this.maplibre = maplibre;
        this.bridge = bridge;
        this.overlays = new Map();
    }

    // WMS 레이어 추가
    addWMS(id, url, options = {}) {
        const wmsLayer = L.tileLayer.wms(url, {
            layers: options.layers,
            styles: options.styles,
            format: 'image/png',
            transparent: options.transparent !== false,
            opacity: options.opacity || 0.7,
            crs: L.CRS.EPSG3857
        });

        // 브릿지를 통해 추가
        this.bridge.addLayer(wmsLayer);
        this.overlays.set(id, wmsLayer);

        // MapLibre 뷰 변경 시 동기화
        this.maplibre.map.on('move', () => {
            const center = this.maplibre.map.getCenter();
            const zoom = this.maplibre.map.getZoom();
            this.bridge.syncView([center.lat, center.lng], zoom);
        });

        return this;
    }

    // 오버레이 가시성
    setVisible(id, visible) {
        const layer = this.overlays.get(id);
        if (layer) {
            visible ? layer.addTo(this.bridge.leafletMap) : layer.remove();
        }
    }

    // 오버레이 불투명도
    setOpacity(id, opacity) {
        const layer = this.overlays.get(id);
        if (layer) {
            layer.setOpacity(opacity);
        }
    }

    // 제거
    remove(id) {
        const layer = this.overlays.get(id);
        if (layer) {
            this.bridge.removeLayer(layer);
            this.overlays.delete(id);
        }
    }
}
```

### 5.4 마커/팝업 호환성

MapLibre의 기본 마커와 팝업을 사용하되, AoT 스타일 적용:

```javascript
/**
 * AoT Popups - MapLibre Popup 스타일링
 */
class AoTPopupManager {
    constructor(map) {
        this.map = map;
        this.popups = new Map();
    }

    // 팝업 생성
    create(id, lngLat, content, options = {}) {
        const popup = new maplibregl.Popup({
            closeButton: true,
            closeOnClick: options.closeOnClick || false,
            maxWidth: options.maxWidth || '350px',
            className: 'aot-popup'
        })
            .setLngLat(lngLat)
            .setHTML(content);

        popup.addTo(this.map);
        this.popups.set(id, popup);
        return popup;
    }

    // 팝업 열기
    open(id) {
        const popup = this.popups.get(id);
        if (popup) popup.addTo(this.map);
    }

    // 팝업 닫기
    close(id) {
        const popup = this.popups.get(id);
        if (popup) popup.remove();
    }

    // 모든 팝업 닫기
    closeAll() {
        this.popups.forEach(p => p.remove());
    }

    // 팝업 업데이트
    update(id, content) {
        const popup = this.popups.get(id);
        if (popup) {
            popup.setHTML(content);
        }
    }

    // 제거
    remove(id) {
        this.close(id);
        this.popups.delete(id);
    }
}
```

CSS 스타일:

```css
/* aot-popup.css */
.aot-popup .maplibregl-popup-content {
    padding: 0;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}

.aot-popup .maplibregl-popup-close-button {
    font-size: 18px;
    padding: 4px 8px;
    color: #666;
}

.aot-popup .aot-popup-content {
    padding: 12px 16px;
}
```

---

## 6. 그리기 도구 마이그레이션

### 6.1 Leaflet.Draw → MapLibre-Geoman 마이그레이션

**선택된 라이브러리**: [MapLibre-Geoman](https://geoman.io/maplibre-geoman)

**이유**:
- Leaflet.Draw API와 유사한 직관적인 인터페이스
- MapLibre-GL 전용 플러그인
- 한국어 지원
- 활발한 커뮤니티

### 6.2 마이그레이션 비교표

| 기능 | Leaflet.Draw | MapLibre-Geoman | 전환 난이도 |
|------|-------------|-----------------|-----------|
| Polyline 그리기 | `L.Draw.Polyline` | `pm.Toolbar.addControls({ polyline: true })` | 낮음 |
| Polygon 그리기 | `L.Draw.Polygon` | `pm.Toolbar.addControls({ polygon: true })` | 낮음 |
| Rectangle 그리기 | `L.Draw.Rectangle` | `pm.Toolbar.addControls({ rectangle: true })` | 낮음 |
| Circle 그리기 | `L.Draw.Circle` | `pm.Toolbar.addControls({ circle: true })` | 중간 |
| Marker 배치 | `L.Draw.Marker` | `pm.Toolbar.addControls({ marker: true })` | 낮음 |
| 편집 모드 | `featureGroup.editing.enable()` | `layer.pm.enable()` | 중간 |
| 삭제 | `layer.remove()` | `layer.pm.remove()` | 낮음 |

### 6.3 MapLibre-Geoman 통합 모듈

```javascript
/**
 * AoT MapLibre Draw - Leaflet.Draw 호환 래퍼
 */
class AoTMapLibreDraw {
    constructor(map, options = {}) {
        this.map = map;
        this.featureGroup = L.featureGroup().addTo(map); // 호환성 유지
        this.options = {
            drawControls: true,
            editControls: true,
            ...options
        };
        this.drawControl = null;
        this._initGeoman();
    }

    _initGeoman() {
        // GeoJSON 소스 생성
        this.map.addSource('draw', {
            type: 'geojson',
            data: { type: 'FeatureCollection', features: [] }
        });

        // 그리기 레이어 추가
        this.map.addLayer({
            id: 'draw-polygon',
            type: 'fill',
            source: 'draw',
            filter: ['==', '$type', 'Polygon'],
            paint: {
                'fill-color': '#28a745',
                'fill-opacity': 0.2
            }
        });

        this.map.addLayer({
            id: 'draw-polygon-outline',
            type: 'line',
            source: 'draw',
            filter: ['==', '$type', 'Polygon'],
            paint: {
                'line-color': '#28a745',
                'line-width': 2
            }
        });

        // Geoman 초기화
        this.map.pm.addControls({
            position: 'topleft',
            drawCircle: false, // Circle은 커스텀 구현
            drawMarker: false,
            drawPolyline: this.options.drawControls,
            drawPolygon: this.options.drawControls,
            drawRectangle: this.options.drawControls,
            editMode: this.options.editControls,
            dragMode: this.options.editControls,
            removalMode: true,
            cutPolygon: false
        });

        // AoT 스타일 적용
        this._applyStyles();
        
        // 이벤트 바인딩
        this._bindEvents();
    }

    _applyStyles() {
        // Geoman 컨트롤 스타일 커스터마이징
        const style = document.createElement('style');
        style.textContent = `
            .maplibregl-pm-toolbar button {
                background: white !important;
                border-radius: 50% !important;
                box-shadow: 0 2px 6px rgba(0,0,0,0.15) !important;
            }
            .maplibregl-pm-toolbar button:hover {
                background: #f0f0f0 !important;
            }
            .maplibregl-pm-toolbar button.active {
                background: #007bff !important;
            }
        `;
        document.head.appendChild(style);
    }

    _bindEvents() {
        // 그리기 완료 이벤트
        this.map.on('pm:create', (e) => {
            const layer = e.layer;
            const feature = layer.toGeoJSON();
            
            // AoT 스타일 적용
            this._applyFeatureStyle(feature);
            
            // 이벤트 발생
            this.featureGroup.fire('draw:created', { layer, feature });
        });

        // 편집 완료 이벤트
        this.map.on('pm:edit', (e) => {
            const layers = e.layers;
            const features = layers.toGeoJSON();
            
            this.featureGroup.fire('draw:edited', { features });
        });

        // 삭제 완료 이벤트
        this.map.on('pm:remove', (e) => {
            const layers = e.layers;
            const features = layers.toGeoJSON();
            
            this.featureGroup.fire('draw:removed', { features });
        });
    }

    _applyFeatureStyle(feature) {
        const type = feature.geometry.type;
        const properties = feature.properties || {};
        const style = this._getStyleByType(properties.type || 'default');

        // 레이어 ID 생성
        const layerId = `draw-${type}-${Date.now()}`;
        
        // 속성 설정
        feature.properties = {
            ...properties,
            ...style
        };
    }

    _getStyleByType(type) {
        const styles = {
            site: { color: '#DF5353', weight: 4 },
            zone: { color: '#28a745', weight: 2, dashArray: '5,5' },
            facility: { color: '#82898f', weight: 3 },
            equipment: { color: '#007bff', weight: 3 },
            aot_device: { color: '#995aff', weight: 2 }
        };
        return styles[type] || styles.zone;
    }

    // 레이어 추가 (외부에서)
    addLayer(geojson) {
        const source = this.map.getSource('draw');
        const data = source._data;
        data.features.push(geojson);
        source.setData(data);
    }

    // GeoJSON 가져오기
    toGeoJSON() {
        const source = this.map.getSource('draw');
        return source._data;
    }

    // 모든 도형 제거
    clear() {
        this.map.getSource('draw').setData({
            type: 'FeatureCollection',
            features: []
        });
    }

    // 특정 도형 제거
    removeLayer(featureId) {
        const source = this.map.getSource('draw');
        const data = source._data;
        data.features = data.features.filter(f => f.id !== featureId);
        source.setData(data);
    }
}
```

### 6.4 기존 AoTMapEditor 호환성

```javascript
/**
 * AoTMapEditor Compatibility Layer
 * 기존 Leaflet.Draw 기반 코드를 MapLibre로 마이그레이션
 */
class AoTMapEditorCompat {
    constructor(map, featureGroup) {
        // MapLibre Draw 인스턴스
        this.draw = new AoTMapLibreDraw(map);
        
        // 레거시 호환성
        this.map = map;
        this.featureGroup = featureGroup || this.draw.featureGroup;
        this.editEnabled = false;
        this.deleteEnabled = false;
    }

    init(map, featureGroup) {
        // 레거시 init 시그니처 지원
        this.map = map;
        this.featureGroup = featureGroup;
        return this;
    }

    setType(type) {
        // 그리기 타입 변경 시 스타일 적용
        this._currentType = type;
        return this;
    }

    startDraw(shape) {
        const shapeMap = {
            'polyline': 'drawPolyline',
            'polygon': 'drawPolygon',
            'rectangle': 'drawRectangle',
            'circle': 'drawCircle'
        };
        
        const method = shapeMap[shape];
        if (method && this.map.pm) {
            this.map.pm.enableDraw(method);
        }
        return this;
    }

    stopDraw() {
        if (this.map.pm) {
            this.map.pm.disableDraw();
        }
        return this;
    }

    enableEdit() {
        this.editEnabled = true;
        if (this.map.pm) {
            this.map.pm.enableGlobalEditMode();
        }
        return this;
    }

    disableEdit() {
        this.editEnabled = false;
        if (this.map.pm) {
            this.map.pm.disableGlobalEditMode();
        }
        return this;
    }

    enableDelete() {
        this.deleteEnabled = true;
        if (this.map.pm) {
            this.map.pm.enableGlobalRemovalMode();
        }
        return this;
    }

    disableDelete() {
        this.deleteEnabled = false;
        if (this.map.pm) {
            this.map.pm.disableGlobalRemovalMode();
        }
        return this;
    }

    stopAll() {
        this.stopDraw();
        this.disableEdit();
        this.disableDelete();
        return this;
    }

    // 레거시 이벤트 핸들러
    on(event, callback) {
        if (this.featureGroup) {
            this.featureGroup.on(event, callback);
        }
        return this;
    }

    off(event, callback) {
        if (this.featureGroup) {
            this.featureGroup.off(event, callback);
        }
        return this;
    }
}
```

---

## 7. 다중 지도 서비스 연동 아키텍처

### 7.1 Supported Providers

| Provider | Type | Status | Transition |
|----------|------|--------|------------|
| VWorld WMTS | Raster | 유지 | 유지 (벡터 전환 고려) |
| VWorld WMS | Raster | 유지 | 유지 |
| MapTiler Vector | Vector | 신규 | 주력 베이스맵 |
| OSM | Raster/Vector | 유지 | Vector 전환 권장 |
| Google Maps | Raster | 유지 | leaflet-googlemutant 유지 |
| Mapbox | Vector | 신규 | Vector 전환 권장 |
| Naver | Raster | 유지 | API 제한으로 유지 |

### 7.2 레이어 스택 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                    Layer Stack (Top to Bottom)               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  UI Layer (z-index: 1500+)                          │   │
│  │  - Controls                                         │   │
│  │  - Popups                                           │   │
│  │  - Search Overlay                                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Data Overlay Layer (z-index: 1000-1500)            │   │
│  │  - WMS Layers (Cadastral, Agricultural, etc.)        │   │
│  │  - Weather Overlays                                 │   │
│  │  - Custom GeoJSON                                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  AoT Feature Layer (z-index: 500-1000)             │   │
│  │  - Device Markers                                   │   │
│  │  - Facility Boundaries                              │   │
│  │  - Drawn Shapes                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Base Map Layer (z-index: 1-500)                   │   │
│  │  ┌───────────────────────────────────────────────┐  │   │
│  │  │  Vector Tile Layer (Primary)                  │  │   │
│  │  │  - MapTiler / OSM / Mapbox                   │  │   │
│  │  └───────────────────────────────────────────────┘  │   │
│  │  ┌───────────────────────────────────────────────┐  │   │
│  │  │  Raster Tile Layer (Fallback/Bridge)         │  │   │
│  │  │  - VWorld / Google / Naver                    │  │   │
│  │  └───────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 7.3 다중 소스 매니저

```javascript
/**
 * AoT Multi-Source Layer Manager
 * 여러 지도 소스를 동적으로 전환/叠加
 */
class AoTMultiSourceManager {
    constructor(map) {
        this.map = map;
        this.sources = new Map();
        this.layers = new Map();
        this.activeBase = null;
    }

    // 벡터 소스 등록
    registerVectorSource(id, config) {
        const source = {
            type: 'vector',
            tiles: config.tiles,
            minzoom: config.minzoom || 0,
            maxzoom: config.maxzoom || 14,
            attribution: config.attribution || ''
        };
        
        this.map.addSource(id, source);
        this.sources.set(id, { type: 'vector', config, source });
        return this;
    }

    // 래스터 소스 등록 (Leaflet 브릿지)
    registerRasterSource(id, config) {
        this.sources.set(id, { type: 'raster', config });
        return this;
    }

    // 베이스맵 전환
    setBaseMap(sourceId) {
        // 현재 베이스맵 숨김
        if (this.activeBase) {
            const current = this.sources.get(this.activeBase);
            if (current) {
                if (current.type === 'vector') {
                    this.map.setLayoutProperty(
                        `${this.activeBase}-base`,
                        'visibility',
                        'none'
                    );
                }
                // Raster는 브릿지에서 처리
            }
        }

        // 새 베이스맵 표시
        const next = this.sources.get(sourceId);
        if (next) {
            if (next.type === 'vector') {
                // 벡터 소스에 베이스 레이어가 없으면 생성
                if (!this.layers.has(`${sourceId}-base`)) {
                    this._createVectorBaseLayer(sourceId, next.config);
                }
                
                this.map.setLayoutProperty(
                    `${sourceId}-base`,
                    'visibility',
                    'visible'
                );
            }
            
            this.activeBase = sourceId;
        }
        
        return this;
    }

    _createVectorBaseLayer(sourceId, config) {
        // MapTiler/OSM 벡터 스타일 레이어
        const style = config.style || 'streets';
        
        // 레이어는 스타일 JSON에 정의되어 있으므로
        // 소스만 추가하면 됨
        this.layers.set(`${sourceId}-base`, true);
    }

    // 오버레이 추가
    addOverlay(id, config) {
        if (config.type === 'wms') {
            // WMS는 브릿지를 통해 추가
            this._addWMSOverlay(id, config);
        } else if (config.type === 'geojson') {
            this._addGeoJSONOverlay(id, config);
        }
        return this;
    }

    _addWMSOverlay(id, config) {
        // Leaflet WMS 브릿지 사용
        // (前述 AoTWMSOverlayManager 참고)
    }

    _addGeoJSONOverlay(id, config) {
        const sourceId = `${id}-source`;
        
        this.map.addSource(sourceId, {
            type: 'geojson',
            data: config.data
        });

        // Fill 레이어
        this.map.addLayer({
            id: `${id}-fill`,
            type: 'fill',
            source: sourceId,
            filter: ['==', '$type', 'Polygon'],
            paint: {
                'fill-color': config.fillColor || '#888',
                'fill-opacity': config.fillOpacity || 0.3
            }
        });

        // Line 레이어
        this.map.addLayer({
            id: `${id}-line`,
            type: 'line',
            source: sourceId,
            filter: ['in', '$type', 'LineString', 'Polygon'],
            paint: {
                'line-color': config.strokeColor || '#333',
                'line-width': config.strokeWidth || 2
            }
        });

        this.layers.set(id, { sourceId, config });
    }

    // 레이어 가시성
    setOverlayVisible(id, visible) {
        const layer = this.layers.get(id);
        if (layer) {
            const visibility = visible ? 'visible' : 'none';
            this.map.setLayoutProperty(`${id}-fill`, 'visibility', visibility);
            this.map.setLayoutProperty(`${id}-line`, 'visibility', visibility);
        }
    }

    // 레이어 스타일 업데이트
    updateOverlayStyle(id, style) {
        if (style.fillColor !== undefined) {
            this.map.setPaintProperty(`${id}-fill`, 'fill-color', style.fillColor);
        }
        if (style.fillOpacity !== undefined) {
            this.map.setPaintProperty(`${id}-fill`, 'fill-opacity', style.fillOpacity);
        }
        if (style.strokeColor !== undefined) {
            this.map.setPaintProperty(`${id}-line`, 'line-color', style.strokeColor);
        }
        if (style.strokeWidth !== undefined) {
            this.map.setPaintProperty(`${id}-line`, 'line-width', style.strokeWidth);
        }
    }

    // 정리
    destroy() {
        this.layers.forEach((layer, id) => {
            if (this.map.getLayer(`${id}-fill`)) {
                this.map.removeLayer(`${id}-fill`);
            }
            if (this.map.getLayer(`${id}-line`)) {
                this.map.removeLayer(`${id}-line`);
            }
            if (this.map.getSource(`${id}-source`)) {
                this.map.removeSource(`${id}-source`);
            }
        });
        
        this.sources.forEach((source, id) => {
            if (this.map.getSource(id)) {
                this.map.removeSource(id);
            }
        });
        
        this.sources.clear();
        this.layers.clear();
    }
}
```

### 7.4 벡터/래스터 전환 로직

```javascript
/**
 * Auto Layer Switcher
 * 네트워크/성능 조건에 따라 벡터 ↔ 래스터 자동 전환
 */
class AoTAutoLayerSwitcher {
    constructor(map, options = {}) {
        this.map = map;
        this.options = {
            preferVector: true,
            minZoomForVector: 10,
            maxZoomForRaster: 12,
            onSwitch: null,
            ...options
        };
        
        this.currentMode = 'vector';
        this._bindEvents();
    }

    _bindEvents() {
        this.map.on('zoomend', () => this._checkSwitch());
        this.map.on('moveend', () => this._checkConnection());
    }

    _checkSwitch() {
        const zoom = this.map.getZoom();
        
        if (this.currentMode === 'vector' && zoom < this.options.minZoomForVector) {
            this._switchToRaster();
        } else if (this.currentMode === 'raster' && zoom >= this.options.maxZoomForRaster) {
            this._switchToVector();
        }
    }

    _checkConnection() {
        // 네트워크 상태 확인 (Performance API 활용)
        const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
        
        if (connection) {
            if (connection.saveData) {
                // 데이터 절약 모드
                this._switchToRaster();
            }
        }
    }

    _switchToVector() {
        if (this.currentMode === 'vector') return;
        
        console.log('[AoT] Switching to Vector tiles');
        this.currentMode = 'vector';
        
        if (this.options.onSwitch) {
            this.options.onSwitch('vector');
        }
    }

    _switchToRaster() {
        if (this.currentMode === 'raster') return;
        
        console.log('[AoT] Switching to Raster tiles');
        this.currentMode = 'raster';
        
        if (this.options.onSwitch) {
            this.options.onSwitch('raster');
        }
    }

    forceMode(mode) {
        this.currentMode = mode;
        if (this.options.onSwitch) {
            this.options.onSwitch(mode);
        }
    }
}
```

---

## 8. 마이그레이션 로드맵

### Phase 1: Foundation (2-3주)

| 작업 | 담당 | 예상 시간 |
|------|------|---------|
| MapLibre-GL 라이브러리 번들 추가 | Frontend | 2일 |
| `aot-maplibre-core.js` 기본 구현 | Frontend | 5일 |
| Leaflet ↔ MapLibre 브릿지 레이어 구현 | Frontend | 3일 |
| WMS 오버레이 통합 테스트 | Frontend | 3일 |
| 기존 JS 번들 빌드 시스템 수정 | DevOps | 2일 |

### Phase 2: Core Features (3-4주)

| 작업 | 담당 | 예상 시간 |
|------|------|---------|
| `AoTMapLibre` 마커/팝업 구현 | Frontend | 5일 |
| `AoTVectorLayerManager` 구현 | Frontend | 5일 |
| `AoTMultiSourceManager` 구현 | Frontend | 5일 |
| MapTiler 벡터 연동 테스트 | Frontend | 3일 |
| OSM 벡터 연동 테스트 | Frontend | 3일 |
| 기존 기능 회귀 테스트 | QA | 3일 |

### Phase 3: Drawing Tools (2-3주)

| 작업 | 담당 | 예상 시간 |
|------|------|---------|
| MapLibre-Geoman 라이브러리 추가 | Frontend | 2일 |
| `AoTMapLibreDraw` 구현 | Frontend | 5일 |
| `AoTMapEditorCompat` 구현 | Frontend | 5일 |
| 그리기 기능 기존 연동 테스트 | Frontend | 3일 |
| 성능 최적화 | Frontend | 3일 |

### Phase 4: Polish & Launch (2주)

| 작업 | 담당 | 예상 시간 |
|------|------|---------|
| UI 스타일링 완료 | Frontend | 3일 |
| 다중 지도 소스 전환 UX | Frontend | 3일 |
| 성능 벤치마크 및 최적화 | Frontend | 3일 |
| 문서 업데이트 | Docs | 2일 |
| 최종 QA 및 버그 수정 | QA | 3일 |

### 전체 일정: 약 9-12주

---

## 9. 참고 문서

### 9.1 외부 참조

| 문서 | URL |
|------|-----|
| MapLibre-GL JS Documentation | https://maplibre.org/maplibre-gl-js/docs/ |
| MapLibre-Geoman | https://geoman.io/maplibre-geoman |
| MapTiler Vector Tiles | https://cloud.maptiler.com/ |
| MVT Specification | https://github.com/mapbox/vector-tile-spec |
| Leaflet-MapLibre Bridge Examples | https://github.com/maplibre/leaflet-maplibre-gl |

### 9.2 내부 문서

| 문서 | 위치 |
|------|------|
| 현재 GIS 문서 | `docs/Supported-Geo-Layers.md` |
| 지도 시스템 개요 | `docs/map.md` |
| GIS 입력 모듈 | `docs/ai_docs/gis_inputs.json` |

### 9.3 DB 문서 (조회 필요)

> ⚠️ 아래 문서들은 DB에서 별도로 조회해야 합니다.

| 문서 ID | 제목 | 조회 방법 |
|--------|------|----------|
| `83810ae7` | GIS 벡터 타일 전환 개요 및 영향 분석 | DB 문서 테이블에서 조회 |
| `6a20936d` | 벡터 엔진 비교 분석 및 권장 사항 | DB 문서 테이블에서 조회 |
| `37a57732` | 다중 지도 서비스 연동 아키텍처 | DB 문서 테이블에서 조회 |
| `b8e7a52c` | 그리기 도구 벡터 전환 가이드 | DB 문서 테이블에서 조회 |

---

## 부록 A: 색상 팔레트

| 용도 | 색상 코드 | 사용처 |
|------|----------|--------|
| Site 경계 | `#DF5353` | 농장/사업장 경계 |
| Zone 경계 | `#28a745` | 작물 구역 |
| Facility | `#82898f` | 시설물 |
| Equipment | `#007bff` | 장비 |
| AoT Device | `#995aff` | IoT 장치 |
| Reference | `#ff00ff` | 참조 레이어 |

## 부록 B: 용어집

| 용어 | 정의 |
|------|------|
| MVT | Mapbox Vector Tile - 바이너리 형식의 벡터 타일 |
| PBF | Protocol Buffer Format - MVT의 인코딩 형식 |
| WMTS | Web Map Tile Service - OGC 표준 래스터 타일 서비스 |
| WMS | Web Map Service - OGC 표준 지도 이미지 서비스 |
| GeoJSON | 지리 공간 데이터를 위한 JSON 형식 |
| CRS | Coordinate Reference System - 좌표 참조 시스템 |

---

**문서 끝**

*본 문서는 아키텍처 설계 단계의 문서로, 구현 과정에서 변경될 수 있습니다.*
