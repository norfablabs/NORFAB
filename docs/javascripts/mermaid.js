/* Mermaid diagrams for MkDocs Material (works with instant navigation) */
(function () {
  function renderMermaid() {
    if (!window.mermaid) return;

    try {
      window.mermaid.initialize({
        startOnLoad: false,
      });

      window.mermaid.run({
        querySelector: ".mermaid",
      });
    } catch (err) {
      // Best-effort: don't break navigation if Mermaid throws.
    }
  }

  if (typeof window.document$ !== "undefined" && window.document$?.subscribe) {
    window.document$.subscribe(renderMermaid);
  } else {
    document.addEventListener("DOMContentLoaded", renderMermaid);
  }
})();
