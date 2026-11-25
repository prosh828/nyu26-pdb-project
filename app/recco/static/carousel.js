// Carousel behaviour for templates/_movies.html rows. Call initCarousels(root)
// again after inserting new rows (the search page does this on every update).
// Also handles the watchlist (+) and hide (thumb down) buttons, on cards and on the watch page.
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

  // --- Watchlist / hide buttons (recco/lists.py) -------------------------------
  // A button with data-action sits inside an element with data-movie-id: a card from
  // templates/_movies.html, or the action bar on the watch page. Clicks are delegated,
  // so cards inserted later (search results) work too.
  var ENDPOINTS = {
    watchlist: function (b) { return ["/api/watchlist/", pressed(b) ? "DELETE" : "PUT"]; },
    hide:      function (b) { return ["/api/hidden/", pressed(b) ? "DELETE" : "PUT"]; },
    unwatch:   function () { return ["/api/watchlist/", "DELETE"]; },
    unhide:    function () { return ["/api/hidden/", "DELETE"]; }
  };
  // Which rows lose the card after an action (section[data-actions] from the macro).
  var REMOVE_FROM = {
    hide:    function (s) { return s.hidden ? 'section[data-actions="browse"]' : null; },
    unwatch: function () { return 'section[data-actions="watchlist"]'; },
    unhide:  function () { return 'section[data-actions="hidden"]'; }
  };

  function pressed(button) { return button.getAttribute("aria-pressed") === "true"; }

  function setPressed(selector, value, onTitle, offTitle) {
    document.querySelectorAll(selector).forEach(function (b) {
      b.setAttribute("aria-pressed", value ? "true" : "false");
      b.title = value ? onTitle : offTitle;
      var label = b.querySelector(".label");
      if (label && b.dataset.onLabel) label.textContent = value ? b.dataset.onLabel : b.dataset.offLabel;
    });
  }

  function removeCards(movieId, sectionSelector) {
    document.querySelectorAll(sectionSelector).forEach(function (section) {
      section.querySelectorAll('.card[data-movie-id="' + movieId + '"]').forEach(function (card) {
        card.classList.add("leaving");
        setTimeout(function () {
          var track = card.parentNode;
          card.remove();
          if (track.querySelector(".card")) {
            track.dispatchEvent(new Event("scroll"));       // re-check the arrows
            return;
          }
          var empty = section.querySelector(".row-empty");
          if (empty) {                                       // My home: say the list is empty
            empty.hidden = false;
            section.querySelector(".carousel").hidden = true;
          } else {
            section.hidden = true;
          }
        }, 200);
      });
    });
  }

  function apply(action, state) {
    var id = state.movie_id, scope = '[data-movie-id="' + id + '"] ';
    setPressed(scope + '[data-action="watchlist"]', state.in_watchlist,
               "Remove from my watchlist", "Add to my watchlist");
    setPressed(scope + '[data-action="hide"]', state.hidden,
               "Hidden - click to show it again", "Not interested (hide)");
    var rows = REMOVE_FROM[action] && REMOVE_FROM[action](state);
    if (rows) removeCards(id, rows);
    // My home lists everything; an addition there (+ on Continue Watching) needs a fresh page.
    if (action === "watchlist" && state.in_watchlist && document.querySelector('section[data-actions="watchlist"]')) {
      location.reload();
    }
  }

  document.addEventListener("click", function (e) {
    var button = e.target.closest("[data-action]");
    var holder = button && button.closest("[data-movie-id]");
    if (!holder || !ENDPOINTS[button.dataset.action] || button.disabled) return;
    e.preventDefault();
    var action = button.dataset.action, ep = ENDPOINTS[action](button);
    button.disabled = true;
    fetch(ep[0] + holder.dataset.movieId, {
      method: ep[1], credentials: "same-origin", headers: { Accept: "application/json" }
    }).then(function (r) {
      if (r.status === 401) { location.href = "/login"; return null; }
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(function (state) {
      if (state) apply(action, state);
    }).catch(function () {
      button.title = "Could not save. Please try again.";
    }).finally(function () {
      button.disabled = false;
    });
  });
})();
