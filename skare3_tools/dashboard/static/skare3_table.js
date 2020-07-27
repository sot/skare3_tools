function set_color_class(e, color) {
  var classes = ['ok-color', 'error-color', 'warning-color', 'highlight-color'];
  for (c in classes) {
    if ( e.classList.contains(c) ) {
      e.classList.remove(c);
    }
  }
  e.classList.add(color);
}
