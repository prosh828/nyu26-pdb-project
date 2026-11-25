// Carousel behaviour for templates/_movies.html rows. Call initCarousels(root)
// again after inserting new rows (the search page does this on every update).
(function () {
  function initCarousel(carousel) {
    if (carousel.dataset.ready) return;
    carousel.dataset.ready = "1";
    var track = carousel.querySelector(".track");
    var prev = carousel.querySelector(".prev");
    var next = carousel.querySelector(".next");
    function update() {
      prev.disabled = track.scrollLeft <= 1;
      next.disabled = track.scrollLeft + track.clientWidth >= track.scrollWidth - 1;
    }
    // Arrow buttons scroll one "page" of posters; an arrow hides at either end.
    prev.addEventListener("click", function () { track.scrollBy({ left: -track.clientWidth * 0.9 }); });
    next.addEventListener("click", function () { track.scrollBy({ left: track.clientWidth * 0.9 }); });
    track.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    update();
  }

  function initPoster(img) {
    // A poster URL that no longer resolves falls back to the title placeholder.
    img.addEventListener("error", function () {
      var span = document.createElement("span");
      span.className = "placeholder";
      span.textContent = img.alt.replace(/ poster$/, "");
      img.replaceWith(span);
    });
  }

  window.initCarousels = function (root) {
    root = root || document;
    root.querySelectorAll(".carousel").forEach(initCarousel);
    root.querySelectorAll(".poster img").forEach(initPoster);
  };
  window.initCarousels(document);
})();
