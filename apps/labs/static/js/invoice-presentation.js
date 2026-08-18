(() => {
  "use strict";

  const root = document.querySelector("[data-presentation]");
  if (!root) return;

  const slides = [...root.querySelectorAll("[data-slide]")];
  const count = root.querySelector("[data-presentation-count]");
  const progress = root.querySelector("[data-presentation-progress]");
  const previous = root.querySelector("[data-presentation-previous]");
  const next = root.querySelector("[data-presentation-next]");
  const stage = root.querySelector(".presentation-stage");
  const sectionNavigation = root.querySelector("[data-presentation-sections]");
  const overview = root.querySelector("[data-presentation-overview-dialog]");
  const overviewList = root.querySelector("[data-presentation-overview-list]");
  const slideMetadata = slides.map((slide, slideIndex) => ({
    index: slideIndex,
    section: slide.dataset.section,
    kicker: slide.dataset.kicker,
    title: slide.dataset.title,
    notes: [...slide.querySelector("[data-speaker-notes]").content.querySelectorAll("li")].map(
      (item) => item.textContent,
    ),
  }));
  const sections = [...new Map(slideMetadata.map((slide) => [slide.section, slide.kicker])).entries()];
  let index = Math.min(
    Math.max(Number.parseInt(location.hash.replace("#slide-", ""), 10) - 1 || 0, 0),
    slides.length - 1,
  );
  let presenterWindow = null;
  let pointerStart = null;

  function sendPresenterState() {
    if (!presenterWindow || presenterWindow.closed) return;
    presenterWindow.postMessage({ type: "presentation-state", index, slides: slideMetadata }, "*");
  }

  function showSlide(nextIndex, updateHash = true) {
    const nextSlideIndex = Math.min(Math.max(nextIndex, 0), slides.length - 1);
    root.dataset.direction = nextSlideIndex < index ? "backward" : "forward";
    index = nextSlideIndex;
    slides.forEach((slide, slideIndex) => {
      slide.classList.toggle("is-active", slideIndex === index);
      slide.setAttribute("aria-hidden", String(slideIndex !== index));
    });
    slides[index].querySelectorAll("[data-reveal]").forEach((element, revealIndex) => {
      element.style.setProperty("--reveal-order", revealIndex);
    });
    slides[index].querySelectorAll(".handoff-flow > b, .architecture-stack > b").forEach((element, arrowIndex) => {
      element.style.setProperty("--arrow-order", arrowIndex);
    });
    count.textContent = `${String(index + 1).padStart(2, "0")} / ${String(slides.length).padStart(2, "0")}`;
    progress.style.width = `${((index + 1) / slides.length) * 100}%`;
    previous.disabled = index === 0;
    next.disabled = index === slides.length - 1;
    sectionNavigation.querySelectorAll("button").forEach((button) => {
      if (button.dataset.section === slideMetadata[index].section) {
        button.setAttribute("aria-current", "step");
      } else {
        button.removeAttribute("aria-current");
      }
    });
    overviewList.querySelectorAll("button").forEach((button, slideIndex) => {
      button.setAttribute("aria-current", String(slideIndex === index));
    });
    if (updateHash) history.replaceState(null, "", `#slide-${index + 1}`);
    document.title = `${slideMetadata[index].title} · Beyond the Chat`;
    sendPresenterState();
  }

  function buildNavigation() {
    for (const [section, label] of sections) {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.section = section;
      button.textContent = label;
      button.addEventListener("click", () => {
        showSlide(slideMetadata.findIndex((slide) => slide.section === section));
      });
      sectionNavigation.append(button);
    }

    for (const slide of slideMetadata) {
      const item = document.createElement("li");
      const button = document.createElement("button");
      const title = document.createElement("strong");
      const kicker = document.createElement("span");
      button.type = "button";
      title.textContent = slide.title;
      kicker.textContent = slide.kicker;
      button.append(title, kicker);
      button.addEventListener("click", () => {
        showSlide(slide.index);
        overview.close();
      });
      item.append(button);
      overviewList.append(item);
    }
  }

  function openPresenter() {
    if (presenterWindow && !presenterWindow.closed) {
      presenterWindow.focus();
      sendPresenterState();
      return;
    }
    presenterWindow = window.open("", "newman-invoice-presenter", "popup,width=1360,height=860");
    if (!presenterWindow) return;
    presenterWindow.document.write(`<!doctype html>
      <html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
      <title>Presenter · Beyond the Chat</title><style>
      :root{--navy:#1a4164;--blue:#286291;--muted:#5b6b77;--border:#d8d4cb;--canvas:#f6f2ef;--surface:#fff}
      *{box-sizing:border-box}body{margin:0;height:100vh;overflow:hidden;color:var(--navy);background:var(--canvas);font:16px Manrope,system-ui,sans-serif}
      main{height:100%;padding:18px;display:grid;grid-template-columns:330px 1fr;gap:18px}aside,section,footer{border:1px solid var(--border);border-radius:12px;background:var(--surface)}
      aside{padding:12px;overflow:auto}ol{margin:0;padding:0;display:grid;gap:6px;list-style:none}li button{width:100%;padding:10px;border:1px solid var(--border);border-radius:7px;color:var(--navy);background:#fff;text-align:left;cursor:pointer}li button.active{color:#fff;background:var(--navy);border-color:var(--navy)}li small{display:block;margin-bottom:4px;opacity:.7;text-transform:uppercase;letter-spacing:.07em}li strong{line-height:1.2}
      .workspace{display:grid;grid-template-rows:auto 1fr auto;gap:18px;min-width:0}.preview{padding:24px;display:grid;grid-template-columns:1fr 1fr;gap:28px}.preview small{color:var(--muted);text-transform:uppercase;letter-spacing:.08em}.preview strong{display:block;margin-top:8px;font-size:30px;line-height:1.08}.notes{padding:32px;overflow:auto}.notes p{margin:0;color:var(--blue);font-weight:700;text-transform:uppercase;letter-spacing:.08em}.notes h1{margin:12px 0 24px;font-size:42px;line-height:1.05}.notes ul{margin:0;padding-left:1.2em;display:grid;gap:18px;font-size:26px;line-height:1.3}footer{min-height:70px;padding:12px 18px;display:flex;align-items:center;justify-content:space-between}footer button{min-height:44px;padding:10px 18px;border:0;border-radius:7px;color:#fff;background:var(--blue);font-weight:700;cursor:pointer}#counter{font:700 20px ui-monospace,monospace}
      </style></head><body><main><aside><ol id="slide-list"></ol></aside><div class="workspace"><section class="preview"><div><small>Current</small><strong id="current"></strong></div><div><small>Next</small><strong id="next"></strong></div></section><section class="notes"><p id="section"></p><h1 id="title"></h1><ul id="notes"></ul></section><footer><button id="previous">← Previous</button><span id="counter"></span><button id="next-button">Next →</button></footer></div></main><script>
      let currentIndex=0;let slides=[];const send=(type)=>window.opener&&window.opener.postMessage({type},'*');
      function render(){const current=slides[currentIndex];const next=slides[Math.min(currentIndex+1,slides.length-1)];if(!current)return;document.getElementById('current').textContent=current.title;document.getElementById('next').textContent=next.title;document.getElementById('section').textContent=current.kicker;document.getElementById('title').textContent=current.title;document.getElementById('notes').replaceChildren(...current.notes.map(note=>{const item=document.createElement('li');item.textContent=note;return item}));document.getElementById('counter').textContent=String(currentIndex+1).padStart(2,'0')+' / '+String(slides.length).padStart(2,'0');document.querySelectorAll('#slide-list button').forEach((button,index)=>button.classList.toggle('active',index===currentIndex))}
      function build(){const list=document.getElementById('slide-list');list.replaceChildren(...slides.map((slide,index)=>{const item=document.createElement('li');const button=document.createElement('button');const small=document.createElement('small');const strong=document.createElement('strong');small.textContent=String(index+1).padStart(2,'0')+' · '+slide.kicker;strong.textContent=slide.title;button.append(small,strong);button.onclick=()=>window.opener&&window.opener.postMessage({type:'goto',index},'*');item.append(button);return item}))}
      window.addEventListener('message',(event)=>{if(event.data?.type!=='presentation-state')return;currentIndex=event.data.index;slides=event.data.slides;build();render()});
      document.getElementById('previous').onclick=()=>send('previous');document.getElementById('next-button').onclick=()=>send('next');document.addEventListener('keydown',(event)=>{if(event.key==='ArrowLeft')send('previous');if(event.key==='ArrowRight'||event.key===' ')send('next')});send('request-state');
      <\/script></body></html>`);
    presenterWindow.document.close();
    sendPresenterState();
  }

  buildNavigation();
  const dateLabel = root.querySelector("[data-presentation-date]");
  if (dateLabel) {
    dateLabel.textContent = new Intl.DateTimeFormat(undefined, {
      month: "long",
      day: "numeric",
      year: "numeric",
    }).format(new Date());
  }

  showSlide(index, false);
  previous.addEventListener("click", () => showSlide(index - 1));
  next.addEventListener("click", () => showSlide(index + 1));
  root.querySelector("[data-presentation-overview]").addEventListener("click", () => overview.showModal());
  root.querySelector("[data-presentation-overview-close]").addEventListener("click", () => overview.close());
  root.querySelector("[data-presentation-presenter]").addEventListener("click", openPresenter);
  root.querySelector("[data-presentation-fullscreen]").addEventListener("click", () => {
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      root.requestFullscreen();
    }
  });

  stage.addEventListener("pointerdown", (event) => {
    if (
      event.pointerType === "mouse" ||
      (event.target instanceof Element && event.target.closest("a, button, pre"))
    ) return;
    pointerStart = { x: event.clientX, y: event.clientY };
  });
  stage.addEventListener("pointerup", (event) => {
    if (!pointerStart) return;
    const horizontalDistance = event.clientX - pointerStart.x;
    const verticalDistance = event.clientY - pointerStart.y;
    pointerStart = null;
    if (Math.abs(horizontalDistance) < 48 || Math.abs(horizontalDistance) <= Math.abs(verticalDistance)) return;
    showSlide(index + (horizontalDistance < 0 ? 1 : -1));
  });
  stage.addEventListener("pointercancel", () => {
    pointerStart = null;
  });

  document.addEventListener("keydown", (event) => {
    if (event.target instanceof Element && event.target.closest("a, button")) return;
    if (["ArrowRight", "PageDown", " "].includes(event.key)) {
      event.preventDefault();
      showSlide(index + 1);
    } else if (["ArrowLeft", "PageUp"].includes(event.key)) {
      event.preventDefault();
      showSlide(index - 1);
    } else if (event.key === "Home") {
      showSlide(0);
    } else if (event.key === "End") {
      showSlide(slides.length - 1);
    } else if (event.key.toLowerCase() === "o") {
      overview.showModal();
    } else if (event.key.toLowerCase() === "p") {
      openPresenter();
    } else if (event.key.toLowerCase() === "f") {
      if (document.fullscreenElement) {
        document.exitFullscreen();
      } else {
        root.requestFullscreen();
      }
    }
  });

  window.addEventListener("message", (event) => {
    if (event.source !== presenterWindow) return;
    if (event.data?.type === "next") showSlide(index + 1);
    if (event.data?.type === "previous") showSlide(index - 1);
    if (event.data?.type === "goto") showSlide(event.data.index);
    if (event.data?.type === "request-state") sendPresenterState();
  });
})();
