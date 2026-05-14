/**
 * Vector Integration Verification Test
 * Run with: node test-vector-integration.js
 * Or include in browser console on aot-flask pages
 */
(function() {
  'use strict';
  
  const results = [];
  const pass = (msg) => { results.push({ status: '✅ PASS', msg }); console.log('✅ PASS:', msg); };
  const fail = (msg) => { results.push({ status: '❌ FAIL', msg }); console.error('❌ FAIL:', msg); };
  
  // Test 1: AoTMapBridge.epsg5179To3857 function exists and is callable
  console.log('\n=== Vector Integration Verification ===\n');
  
  // Mock global for Node.js test environment
  if (typeof window === 'undefined') {
    global.window = { 
      AOT_MAP_LOADER: {},
      L: { latLngBounds: () => ({ getWest: () => 0, getSouth: () => 0, getEast: () => 0, getNorth: () => 0 }) }
    };
  }
  
  // Test EPSG coordinate transform with known values
  // Daegu area coordinates in EPSG:5179 (Korea Central Belt)
  // Approx: EPSG:5179 X=485000, Y=260000 should map to EPSG:3857 [128.6, 35.9]
  const test_x = 485000;
  const test_y = 260000;
  
  try {
    // AoTMapBridge should be globally available after layout_default.html loads
    if (typeof AoTMapBridge !== 'undefined') {
      pass('AoTMapBridge namespace exists');
      
      if (typeof AoTMapBridge.epsg5179To3857 === 'function') {
        pass('AoTMapBridge.epsg5179To3857() is a function');
        
        // Functional call test
        const result = AoTMapBridge.epsg5179To3857(test_x, test_y);
        if (result && Array.isArray(result) && result.length === 2) {
          pass(`epsg5179To3857(${test_x}, ${test_y}) => [${result[0].toFixed(4)}, ${result[1].toFixed(4)}]`);
          
          // Sanity check: result should be near Daegu (lng ~128.6, lat ~35.9)
          if (Math.abs(result[0] - 128.6) < 0.5 && Math.abs(result[1] - 35.9) < 0.5) {
            pass('Transform result is geographically reasonable (near Daegu, Korea)');
          } else {
            fail('Transform result outside expected range for Daegu area');
          }
        } else {
          fail('epsg5179To3857 did not return expected [lng, lat] array');
        }
      } else {
        fail('AoTMapBridge.epsg5179To3857 is not a function');
      }
      
      if (typeof AoTMapBridge.create === 'function') {
        pass('AoTMapBridge.create() factory exists');
      }
      
      if (typeof AoTMapBridge.wgs84To3857 === 'function') {
        pass('AoTMapBridge.wgs84To3857() coordinate transform exists');
      }
    } else {
      fail('AoTMapBridge namespace not found (ensure layout_default.html is loaded)');
    }
  } catch (e) {
    fail('Exception: ' + e.message);
  }
  
  // Test 2: AoTVectorLayerManager exists
  try {
    if (typeof AoTVectorLayerManager !== 'undefined') {
      pass('AoTVectorLayerManager namespace exists');
      
      if (typeof AoTVectorLayerManager.create === 'function') {
        pass('AoTVectorLayerManager.create() factory exists');
        
        const manager = AoTVectorLayerManager.create();
        if (manager && typeof manager.addLayer === 'function') {
          pass('AoTVectorLayerManager instance has addLayer() method');
        }
      }
    } else {
      fail('AoTVectorLayerManager namespace not found');
    }
  } catch (e) {
    fail('Exception: ' + e.message);
  }
  
  // Test 3: AoTRasterBridge exists
  try {
    if (typeof AoTRasterBridge !== 'undefined') {
      pass('AoTRasterBridge namespace exists');
      
      if (typeof AoTRasterBridge.create === 'function') {
        pass('AoTRasterBridge.create() factory exists');
      }
    } else {
      fail('AoTRasterBridge namespace not found');
    }
  } catch (e) {
    fail('Exception: ' + e.message);
  }
  
  // Test 4: AoTMapLibre exists (from bundle)
  try {
    if (typeof AoTMapLibre !== 'undefined') {
      pass('AoTMapLibre namespace exists (bundle)');
      
      if (typeof AoTMapLibre.init === 'function') {
        pass('AoTMapLibre.init() method exists');
      }
    }
  } catch (e) {
    fail('Exception: ' + e.message);
  }
  
  // Summary
  console.log('\n=== Summary ===');
  const passed = results.filter(r => r.status.includes('PASS')).length;
  const failed = results.filter(r => r.status.includes('FAIL')).length;
  console.log(`Total: ${results.length} | Passed: ${passed} | Failed: ${failed}`);
  
  if (failed === 0) {
    console.log('🎉 All tests passed!');
  } else {
    console.log('⚠️  Some tests failed - review above');
  }
  
  return { passed, failed, results };
})();
