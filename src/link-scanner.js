export async function scanAndFixLinks(env) {
  const db = env.DB;
  const [pagesRes, newsRes] = await Promise.all([
    db.prepare("SELECT slug FROM pages WHERE status='live'").all(),
    db.prepare("SELECT slug FROM news WHERE status='live'").all(),
  ]);
  const knownSlugs = new Set([...pagesRes.results.map(r=>r.slug),...newsRes.results.map(r=>r.slug)]);
  let totalLinks=0,brokenFound=0,autoFixed=0,unfixable=0;
  let offset=0;
  const deadline = Date.now() + 25_000;
  try {
    while(true){
      if(Date.now() > deadline) break;
      const batch=await db.prepare("SELECT slug,html FROM pages WHERE status='live' LIMIT 100 OFFSET ?").bind(offset).all();
      if(!batch.results.length)break;
      offset+=100;
      for(const page of batch.results){
        if(Date.now() > deadline) break;
        if(!page.html)continue;
        const hrefRegex=/href="(\/[^"#?][^"]*?)"/g;
        let match,newHtml=page.html,pageModified=false;
        while((match=hrefRegex.exec(page.html))!==null){
          totalLinks++;
          const rawHref=match[1];
          const slug=rawHref.split('?')[0].split('#')[0].replace(/^\//,'').replace(/\/$/,'');
          if(!slug||knownSlugs.has(slug))continue;
          const existing=await db.prepare("SELECT id,status FROM broken_links WHERE source_slug=? AND broken_href=?").bind(page.slug,rawHref).first();
          if(existing&&existing.status!=='pending')continue;
          brokenFound++;
          const brokenWords=slug.split('-').filter(w=>w.length>2);
          let bestSlug=null,bestScore=0;
          for(const candidate of knownSlugs){const shared=brokenWords.filter(w=>candidate.split('-').includes(w)).length;if(shared>bestScore){bestScore=shared;bestSlug=candidate;}}
          if(bestScore>=2&&bestSlug){
            newHtml=newHtml.replaceAll(`href="${rawHref}"`,`href="/${bestSlug}"`);
            pageModified=true;autoFixed++;
            if(existing){await db.prepare("UPDATE broken_links SET status='fixed',suggested_slug=?,fixed_at=datetime('now') WHERE id=?").bind(bestSlug,existing.id).run();}
            else{await db.prepare("INSERT INTO broken_links(source_slug,broken_href,suggested_slug,status,fixed_at)VALUES(?,?,?,'fixed',datetime('now'))").bind(page.slug,rawHref,bestSlug).run();}
          }else{
            unfixable++;
            if(!existing){await db.prepare("INSERT OR IGNORE INTO broken_links(source_slug,broken_href,status)VALUES(?,?,'unfixable')").bind(page.slug,rawHref).run();}
          }
        }
        if(pageModified)await db.prepare("UPDATE pages SET html=? WHERE slug=?").bind(newHtml,page.slug).run();
      }
    }
  } finally {
    await db.prepare("INSERT INTO link_scan_log(total_links,broken_found,auto_fixed,unfixable)VALUES(?,?,?,?)").bind(totalLinks,brokenFound,autoFixed,unfixable).run();
    console.log(`✅ Link scan: ${totalLinks} links, ${brokenFound} broken, ${autoFixed} fixed, ${unfixable} unfixable`);
  }
}
