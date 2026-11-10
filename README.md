# ryanwien.github.io

My portfolio front door: one page for my fintech work. It leads with the verified headline
numbers, shows the five systems with their real metrics, plays the 21 second video tour, and
links straight to the live dashboard. Plain HTML and CSS, no framework, no build step.

**Live:** [ryanwien.github.io](https://ryanwien.github.io/)
**The work:** [FintechPortfolio dashboard](https://ryanwien.github.io/FintechPortfolio/) with live demos of every system, and the [source on GitHub](https://github.com/ryanwien/FintechPortfolio).

## Layout

```
index.html        the page
assets/style.css  tokens, layout, responsive rules (dark by default, light by preference)
assets/img/       screenshots and the order book GIF, captured from the live sites
assets/media/     the 21 second video tour and the one-page PDF
```

## Run it locally

```bash
python -m http.server 8000
```

Then open http://localhost:8000. Numbers on the page come from the fintech repo's committed
results; update them when those change.
