// aot-geo-parcel-import.js
// VWorld 주소 → 필지 폴리곤 → AoT Site 변환 모듈
// @module AoTParcelImport
// @version 20260506a

const AoTParcelImport = {
    _previewFeatures: [],   // 현재 미리보기 중인 GeoJSON Feature 배열
    _mapInstance: null,     // 외부에서 주입 받는 maplibre Map 인스턴스
    SOURCE_ID: 'aot-parcel-preview',
    FILL_ID: 'aot-parcel-preview-fill',
    LINE_ID: 'aot-parcel-preview-line',

    /** 초기화: map 인스턴스 주입 */
    init: function(map) { this._mapInstance = map; },

    /** 단일 주소로 필지 조회 — API Key는 서버에서 VWorld GIS Input 설정값을 자동 사용 */
    searchAddress: async function(address) {
        const resp = await fetch('/api/geo/parcel/from_address', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': window._csrf || ''},
            body: JSON.stringify({address})
        });
        return resp.json();
    },

    /** CSV 파일 배치 조회 — API Key는 서버에서 VWorld GIS Input 설정값을 자동 사용 */
    uploadCsv: async function(file) {
        const fd = new FormData();
        fd.append('file', file);
        const resp = await fetch('/api/geo/parcel/from_csv', {
            method: 'POST',
            headers: {'X-CSRFToken': window._csrf || ''},
            body: fd
        });
        return resp.json();
    },

    /** 미리보기 레이어를 지도에 표시 */
    showPreview: function(features) {
        this._previewFeatures = features;
        const map = this._mapInstance;
        if (!map) return;
        const geojson = {type: 'FeatureCollection', features: features};
        const doAdd = () => {
            if (map.getSource(this.SOURCE_ID)) {
                map.getSource(this.SOURCE_ID).setData(geojson);
            } else {
                map.addSource(this.SOURCE_ID, {type: 'geojson', data: geojson});
                map.addLayer({id: this.FILL_ID, type: 'fill', source: this.SOURCE_ID,
                    paint: {'fill-color': '#DF5353', 'fill-opacity': 0.25}});
                map.addLayer({id: this.LINE_ID, type: 'line', source: this.SOURCE_ID,
                    paint: {'line-color': '#DF5353', 'line-width': 2}});
            }
            // 전체 영역으로 이동
            if (features.length > 0) {
                try {
                    const bounds = features.reduce((b, f) => {
                        const coords = this._flatCoords(f.geometry);
                        coords.forEach(c => b.extend(c));
                        return b;
                    }, new maplibregl.LngLatBounds());
                    map.fitBounds(bounds, {padding: 60, maxZoom: 19});
                } catch(e) {}
            }
        };
        if (map.isStyleLoaded()) doAdd(); else map.once('load', doAdd);
    },

    /** 미리보기 제거 */
    clearPreview: function() {
        this._previewFeatures = [];
        const map = this._mapInstance;
        if (!map) return;
        try { if(map.getLayer(this.FILL_ID)) map.removeLayer(this.FILL_ID); } catch(e){}
        try { if(map.getLayer(this.LINE_ID)) map.removeLayer(this.LINE_ID); } catch(e){}
        try { if(map.getSource(this.SOURCE_ID)) map.removeSource(this.SOURCE_ID); } catch(e){}
    },

    /** 인접 폴리곤 union (turf.js v7 API: featureCollection 단일 인수) */
    mergeAdjacent: function(features) {
        if (!window.turf || features.length <= 1) return features;
        try {
            // turf v7: union(FeatureCollection) — v6처럼 (a, b) 2인수 아님
            const fc = turf.featureCollection(features.map(f => {
                // Polygon/MultiPolygon만 union 가능 — 속성 보존
                return turf.feature(f.geometry, f.properties || {});
            }));
            const merged = turf.union(fc);
            if (!merged) throw new Error('union returned null');
            // 이름: 첫 번째 필지 + 외 N개
            const name = (features[0].properties && features[0].properties.name) || '대지';
            const extra = features.length > 1 ? ` 외 ${features.length - 1}필지` : '';
            merged.properties = merged.properties || {};
            merged.properties.name = name + extra;
            return [merged];
        } catch(e) {
            console.warn('[AoTParcelImport] turf.union failed:', e);
            return features;
        }
    },

    /** Site로 저장 (단일 또는 병합 결과) */
    saveAsSite: async function(feature, name, mapUuid) {
        const resp = await fetch('/api/geo/parcel/save_as_site', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': window._csrf || ''},
            body: JSON.stringify({feature, name, map_uuid: mapUuid})
        });
        return resp.json();
    },

    /** geometry에서 좌표 배열 추출 (bounds 계산용) */
    _flatCoords: function(geometry) {
        if (!geometry) return [];
        const flatten = (arr) => {
            if (!Array.isArray(arr)) return [];
            if (typeof arr[0] === 'number') return [arr];
            return arr.flatMap(flatten);
        };
        return flatten(geometry.coordinates);
    }
};

window.AoTParcelImport = AoTParcelImport;
