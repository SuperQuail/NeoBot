const paths = {
  search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  refresh: <><path d="M20 7v5h-5M4 17v-5h5" /><path d="M6 7a7 7 0 0 1 12-1l2 6M4 12l2 6a7 7 0 0 0 12-1" /></>,
  save: <><path d="M5 3h12l4 4v14H3V3z" /><path d="M7 3v6h9V3M7 21v-8h10v8" /></>,
  play: <path d="m8 5 11 7-11 7z" />,
  pause: <path d="M8 5v14M16 5v14" />,
  trash: <><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7" /></>,
  external: <path d="M14 3h7v7M21 3 10 14M10 3H3v18h18v-7" />,
  code: <path d="m7 7-5 5 5 5M17 7l5 5-5 5M14 4l-4 16" />,
  settings: <><path d="M4 7h16M4 17h16" /><circle cx="8" cy="7" r="2" /><circle cx="16" cy="17" r="2" /></>,
  package: <path d="m12 3 9 5v9l-9 5-9-5V8zM3 8l9 5 9-5M12 13v9M7 5.8l9 5" />,
  check: <path d="m5 12 4 4L19 6" />,
  chevron: <path d="m9 5 7 7-7 7" />,
  back: <path d="m14 5-7 7 7 7" />,
  eye: <><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></>,
  more: <><circle cx="5" cy="12" r="1" /><circle cx="12" cy="12" r="1" /><circle cx="19" cy="12" r="1" /></>,
  download: <path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5" />,
  undo: <path d="M4 10h10a6 6 0 0 1 0 12M4 10l5-5M4 10l5 5" />,
};

export default function Icon({ name, ...props }) {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths[name]}</svg>;
}
