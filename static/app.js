document.addEventListener("DOMContentLoaded", () => {
  if (sessionStorage.getItem("vezzallo-cart-added")) {
    document.querySelector(".cart-badge")?.classList.add("bump");
    sessionStorage.removeItem("vezzallo-cart-added");
  }
  const menuToggle = document.getElementById("menu-toggle");
  const navBar = document.getElementById("nav-bar");
  const backdrop = document.getElementById("menu-backdrop");
  const searchToggle = document.getElementById("search-toggle");
  const searchInput = document.getElementById("site-search");
  const setMenuOpen = (open, focusSearch = false) => {
    document.body.classList.toggle("menu-open", open);
    if (menuToggle) menuToggle.setAttribute("aria-expanded", String(open));
    if (focusSearch && searchInput) {
      window.setTimeout(() => searchInput.focus(), 220);
    }
  };
  if (menuToggle && navBar) menuToggle.addEventListener("click", () => {
    setMenuOpen(!document.body.classList.contains("menu-open"));
  });
  if (backdrop) backdrop.addEventListener("click", () => setMenuOpen(false));
  if (searchToggle) searchToggle.addEventListener("click", () => {
    setMenuOpen(true, true);
  });
  if (navBar) {
    navBar.querySelectorAll("a").forEach((link) => link.addEventListener("click", () => setMenuOpen(false)));
  }
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setMenuOpen(false);
  });

  const quantityInput = document.getElementById("quantity");
  const buyNowQuantity = document.querySelector('form[action*="/buy-now/"] input[name="quantity"]');
  if (quantityInput && buyNowQuantity) {
    quantityInput.addEventListener("input", () => {
      buyNowQuantity.value = quantityInput.value;
    });
  }

  document.querySelectorAll("[data-search-form]").forEach((form) => {
    const search = form.querySelector('input[type="search"]');
    const suggestions = form.querySelector(".search-suggestions");
    let searchTimer;
    if (!search || !suggestions) return;
    search.addEventListener("input", () => {
      window.clearTimeout(searchTimer);
      const query = search.value.trim();
      if (query.length < 2) {
        suggestions.replaceChildren();
        suggestions.style.display = "none";
        return;
      }
      searchTimer = window.setTimeout(async () => {
        try {
          const response = await fetch(`/search/suggest?q=${encodeURIComponent(query)}`);
          if (!response.ok) throw new Error(`Search suggestions failed: ${response.status}`);
          const data = await response.json();
          suggestions.replaceChildren();
          data.products.forEach((product) => {
            const link = document.createElement("a");
            link.href = product.url;
            link.textContent = product.name;
            suggestions.append(link);
          });
          suggestions.style.display = data.products.length ? "block" : "none";
        } catch (error) {
          console.error("Could not load search suggestions.", error);
          suggestions.replaceChildren();
          suggestions.style.display = "none";
        }
      }, 180);
    });
    document.addEventListener("click", (event) => {
      if (!suggestions.contains(event.target) && event.target !== search) suggestions.style.display = "none";
    });
  });

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const heroImage = document.querySelector(".hero-product-image");
  if (heroImage && !reducedMotion) {
    const heroArt = heroImage.closest(".premium-hero-art");
    heroArt?.addEventListener("pointermove", (event) => {
      if (event.pointerType === "touch") return;
      const bounds = heroArt.getBoundingClientRect();
      const x = (event.clientX - bounds.left) / bounds.width - 0.5;
      const y = (event.clientY - bounds.top) / bounds.height - 0.5;
      heroImage.style.setProperty("--tilt-x", `${(-y * 7).toFixed(1)}deg`);
      heroImage.style.setProperty("--tilt-y", `${(x * 9).toFixed(1)}deg`);
    });
    heroArt?.addEventListener("pointerleave", () => {
      heroImage.style.removeProperty("--tilt-x");
      heroImage.style.removeProperty("--tilt-y");
    });
  }

  const revealItems = document.querySelectorAll(".reveal-on-scroll");
  if ("IntersectionObserver" in window && !reducedMotion) {
    const revealObserver = new IntersectionObserver((entries, observer) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08 });
    revealItems.forEach((item) => revealObserver.observe(item));
  } else {
    revealItems.forEach((item) => item.classList.add("is-visible"));
  }

  document.querySelectorAll("[data-carousel]").forEach((carousel) => {
    const slides = Array.from(carousel.querySelectorAll(".carousel-slide"));
    if (slides.length < 2) return;
    const dots = Array.from(carousel.querySelectorAll("[data-carousel-dot]"));
    const progress = carousel.querySelector("[data-carousel-progress]");
    const interval = Math.max(1000, Number(carousel.dataset.interval) || 3000);
    let active = slides.findIndex((slide) => slide.classList.contains("is-active"));
    let timer;
    const showSlide = (index) => {
      active = (index + slides.length) % slides.length;
      slides.forEach((slide, slideIndex) => {
        const isActive = slideIndex === active;
        slide.classList.toggle("is-active", isActive);
        slide.setAttribute("aria-hidden", String(!isActive));
      });
      dots.forEach((dot, dotIndex) => {
        const isActive = dotIndex === active;
        dot.classList.toggle("is-active", isActive);
        dot.setAttribute("aria-current", String(isActive));
      });
      if (progress) {
        progress.classList.remove("is-running");
        progress.style.animationDuration = `${interval}ms`;
        void progress.offsetWidth;
        if (!reducedMotion) progress.classList.add("is-running");
      }
    };
    const stop = () => {
      window.clearInterval(timer);
      timer = undefined;
      if (progress) progress.classList.remove("is-running");
    };
    const start = () => {
      stop();
      if (!reducedMotion && !document.hidden) {
        if (progress) {
          progress.style.animationDuration = `${interval}ms`;
          void progress.offsetWidth;
          progress.classList.add("is-running");
        }
        timer = window.setInterval(() => showSlide(active + 1), interval);
      }
    };
    let pointerStart;
    carousel.addEventListener("pointerdown", (event) => {
      if (event.pointerType === "mouse" && event.button !== 0) return;
      pointerStart = { x: event.clientX, y: event.clientY };
    });
    carousel.addEventListener("pointerup", (event) => {
      if (!pointerStart) return;
      const deltaX = event.clientX - pointerStart.x;
      const deltaY = event.clientY - pointerStart.y;
      pointerStart = undefined;
      if (Math.abs(deltaX) < 45 || Math.abs(deltaX) < Math.abs(deltaY)) return;
      showSlide(active + (deltaX < 0 ? 1 : -1));
      start();
    });
    carousel.addEventListener("pointercancel", () => { pointerStart = undefined; });
    carousel.querySelector("[data-carousel-prev]")?.addEventListener("click", () => {
      showSlide(active - 1);
      start();
    });

    document.querySelectorAll("[data-scroll-target]").forEach((button) => {
      button.addEventListener("click", () => {
        const scroller = document.getElementById(button.dataset.scrollTarget);
        if (!scroller) return;
        const direction = Number(button.dataset.scrollDirection) || 1;
        const rtl = window.getComputedStyle(scroller).direction === "rtl";
        scroller.scrollBy({
          left: direction * scroller.clientWidth * 0.78 * (rtl ? -1 : 1),
          behavior: reducedMotion ? "auto" : "smooth",
        });
      });
    });
    carousel.querySelector("[data-carousel-next]")?.addEventListener("click", () => {
      showSlide(active + 1);
      start();
    });
    dots.forEach((dot) => dot.addEventListener("click", () => {
      showSlide(Number(dot.dataset.carouselDot));
      start();
    }));
    carousel.addEventListener("mouseenter", stop);
    carousel.addEventListener("mouseleave", start);
    carousel.addEventListener("focusin", stop);
    carousel.addEventListener("focusout", (event) => {
      if (!carousel.contains(event.relatedTarget)) start();
    });
    document.addEventListener("visibilitychange", start);
    start();
  });

  if (window.fbq && document.querySelector(".detail-card")) {
    const product = document.querySelector(".detail-card");
    window.fbq("track", "ViewContent", {
      content_name: product.dataset.itemName,
      value: Number(product.dataset.value),
      currency: "MAD",
    });
  }
  if (window.ttq && document.querySelector(".detail-card")) {
    const product = document.querySelector(".detail-card");
    window.ttq.track("ViewContent", {
      content_name: product.dataset.itemName,
      value: Number(product.dataset.value),
      currency: "MAD",
    });
  }
  if (window.gtag && document.querySelector(".detail-card")) {
    window.gtag("event", "view_item");
  }
  if (window.fbq && document.querySelector(".checkout-page")) {
    window.fbq("track", "InitiateCheckout", {
      value: Number(document.querySelector(".checkout-page").dataset.value),
      currency: "MAD",
    });
  }
  if (window.ttq && document.querySelector(".checkout-page")) {
    window.ttq.track("InitiateCheckout", {
      value: Number(document.querySelector(".checkout-page").dataset.value),
      currency: "MAD",
    });
  }
  if (window.gtag && document.querySelector(".checkout-page")) {
    window.gtag("event", "begin_checkout");
  }
  document.querySelectorAll('form[action*="/cart/add/"]').forEach((form) => {
    form.addEventListener("submit", () => {
      const quantity = Number(form.querySelector('[name="quantity"]')?.value || 1);
      const value = Number(form.dataset.value || 0) * quantity;
      if (window.fbq) window.fbq("track", "AddToCart", { value, currency: "MAD" });
      if (window.ttq) window.ttq.track("AddToCart", { value, currency: "MAD" });
      if (window.gtag) window.gtag("event", "add_to_cart", { value, currency: "MAD" });
      const button = form.querySelector(".product-add-button");
      const badge = document.querySelector(".cart-badge");
      sessionStorage.setItem("vezzallo-cart-added", "1");
      if (button) button.classList.add("is-added");
      if (badge) {
        badge.classList.remove("bump");
        requestAnimationFrame(() => badge.classList.add("bump"));
      }
    });
  });

  document.querySelectorAll(".hero-product-image").forEach((image) => {
    image.addEventListener("load", () => image.classList.add("image-ready"), { once: true });
  });
  document.querySelectorAll("img[data-fallback]").forEach((image) => {
    const useFallback = () => {
      const fallback = image.dataset.fallback;
      if (fallback) {
        image.dataset.fallback = "";
        image.src = fallback;
      } else {
        image.hidden = true;
      }
    };
    image.addEventListener("error", useFallback);
    if (image.complete && image.naturalWidth === 0) useFallback();
  });

  document.querySelectorAll(".newsletter-form").forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const email = form.querySelector("input[type=email]")?.value.trim();
      const contact = form.dataset.email;
      if (email && contact) {
        const subject = encodeURIComponent("Vezzallo newsletter subscription");
        const body = encodeURIComponent(`Please add ${email} to the newsletter.`);
        window.location.href = `mailto:${contact}?subject=${subject}&body=${body}`;
      } else if (email) {
        const status = form.parentElement.querySelector(".newsletter-status");
        if (status) status.textContent = form.dataset.notConfigured;
      }
    });
  });
});
