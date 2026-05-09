import resolve from '@rollup/plugin-node-resolve';
import commonjs from '@rollup/plugin-commonjs';
import terser from '@rollup/plugin-terser';

const production = process.env.NODE_ENV === 'production';

export default [
  // Development bundle (with sourcemap)
  {
    input: 'src/index.js',
    output: {
      file: 'dist/aot-geo.bundle.js',
      format: 'iife',
      name: 'AoTGeo',
      sourcemap: true,
      globals: {
        'leaflet': 'L'
      }
    },
    external: ['leaflet'],
    plugins: [
      resolve(),
      commonjs()
    ]
  },
  
  // Production bundle (minified)
  {
    input: 'src/index.js',
    output: {
      file: 'dist/aot-geo.bundle.min.js',
      format: 'iife',
      name: 'AoTGeo',
      sourcemap: true,
      globals: {
        'leaflet': 'L'
      }
    },
    external: ['leaflet'],
    plugins: [
      resolve(),
      commonjs(),
      terser({
        compress: {
          drop_console: production,
          drop_debugger: production,
          passes: 2
        },
        mangle: {
          properties: false
        },
        format: {
          comments: false
        }
      })
    ]
  }
];
