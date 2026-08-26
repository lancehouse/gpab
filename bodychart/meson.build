project('bodychart', 'c',
  version : '0.1.0',
  default_options : ['warning_level=2', 'c_std=c11'])

gtk4_dep    = dependency('gtk4')
cairo_dep   = dependency('cairo')
rsvg_dep    = dependency('librsvg-2.0')
jsonc_dep   = dependency('json-c')
m_dep       = meson.get_compiler('c').find_library('m', required : false)
# Embeds gpab's Python assessment app in this process via CPython — see
# src/py_embed.c/.h. Developed and proven on a third-tier `merged-app`
# worktree (see CLAUDE.md's "Branch and deployment rules"), promoted to
# dev/gpabd's own build 2026-08-26. main/gpabs has NOT received this yet.
python_dep  = dependency('python3-embed')

sources = files(
  'src/main.c',
  'src/window.c',
  'src/canvas.c',
  'src/input.c',
  'src/stroke.c',
  'src/body_outlines.c',
  'src/svg_views.c',
  'src/overlays.c',
  'src/overlay_svg.c',
  'src/session.c',
  'src/settings.c',
  'src/persistence.c',
  'src/integration.c',
  'src/py_embed.c',
  'src/obj_chart.c',
  'src/report.c',
  'src/svg_regions.c',
  'src/overlay_data/dermatomes.c',
  'src/overlay_data/peripheral.c',
  'src/overlay_data/somatic.c',
)

executable('bodychart',
  sources,
  dependencies : [gtk4_dep, cairo_dep, rsvg_dep, jsonc_dep, m_dep, python_dep],
  install : true)

install_data('data/com.pab.bodychart.desktop',
  install_dir : get_option('datadir') / 'applications')

foreach size : ['16x16', '22x22', '24x24', '32x32', '48x48', '64x64', '128x128', '256x256', '512x512', '1024x1024']
  install_data('data/icons/hicolor' / size / 'apps/com.pab.bodychart.png',
    install_dir : get_option('datadir') / 'icons/hicolor' / size / 'apps')
endforeach

gnome = import('gnome')
gnome.post_install(
  gtk_update_icon_cache : true,
)
