const paths: Record<string,string> = {
  globe:'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM3 12h18M12 3c4 5 4 13 0 18-4-5-4-13 0-18Z',
  tour:'M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2Zm3.6 6.4-2.1 5.1-5.1 2.1 2.1-5.1 5.1-2.1Z',
  layers:'m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5',
  compare:'M12 3v18M8 7H4v10h4m8-10h4v10h-4',
  chart:'M4 4v16h16M7 14l4-5 4 3 5-7',
  info:'M12 11v6m0-10v.1M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
  pin:'M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Zm-4 0a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',
  close:'m6 6 12 12M6 18 18 6', search:'m16 16 5 5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z',
  arrow:'M5 12h14m-5-5 5 5-5 5', home:'m3 10 9-7 9 7M5 9v12h14V9M9 21v-8h6v8',
};
export function Icon({name,size=20}:{name:string;size?:number}) {return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name] ?? paths.info}/></svg>}
