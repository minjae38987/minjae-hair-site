// Public deployment audit. Checks the LIVE GitHub Pages response, never GA4 reports.
// This test runs after main is updated, with a short retry window for Pages propagation.
const base = 'https://minjae38987.github.io/minjae-hair-site/';
const paths = ['', 'styles/mens-leaf-cut-before-after/', 'styles/mens-leaf-volume-perm/', 'styles/mens-down-perm-guide/'];
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function get(url) {
  const response = await fetch(url, {redirect:'follow', signal:AbortSignal.timeout(20000), headers:{'user-agent':'MinjaeSEODeploymentAudit/1.0'}});
  const body = await response.text();
  if (response.status !== 200) throw new Error(url + ' returned HTTP '+response.status);
  return {body, response};
}
async function inspect() {
  const xml = (await get(base+'sitemap.xml')).body;
  const actual = [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map(m => m[1]);
  const expected = paths.map(p=>base+p);
  if (JSON.stringify(actual)!==JSON.stringify(expected)) throw new Error('Live sitemap URL mismatch: '+JSON.stringify(actual));
  const results = [];
  for (const path of paths) {
    const url = base+path;
    const {body,response} = await get(url);
    const canonical=body.match(/<link rel="canonical" href="([^"]+)"/)?.[1];
    const title=body.match(/<title>([^<]+)<\/title>/)?.[1];
    const description=body.match(/<meta name="description" content="([^"]+)"/)?.[1];
    if(canonical!==url)throw new Error('Canonical mismatch: '+url+' => '+canonical);
    if(!title || !description)throw new Error('Missing SEO title/description: '+url);
    if(!/<h1(?:\s|>)/.test(body))throw new Error('Missing H1: '+url);
    if(!body.includes('G-HJ7ZN6WJWH') && !body.includes('assets/ga4-consent.js'))throw new Error('Analytics module missing: '+url);
    const scripts=[...body.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g)].map(m=>JSON.parse(m[1]));
    if(!scripts.length)throw new Error('No JSON-LD: '+url);
    const nodes=scripts.flatMap(obj=>obj['@graph']||[obj]);
    if(path){
      const breadcrumb=nodes.find(x=>x['@type']==='BreadcrumbList');
      const page=nodes.find(x=>x['@type']==='WebPage');
      if(!breadcrumb || !page || page.breadcrumb?.['@id']!==url+'#breadcrumb')throw new Error('Missing live breadcrumb link: '+url);
    }else{
      const embeds=[...body.matchAll(/<iframe[^>]*instagram\.com\/reel\/[^>]*>/g)];
      if(embeds.length!==10 || embeds.some(m=>/\ssrc=/.test(m[0]))) throw new Error('Gallery has early-loading iframe on live homepage');
    }
    results.push({url,status:response.status,bytes:Buffer.byteLength(body),title,canonical,jsonLdNodes:nodes.length});
  }
  return results;
}
let error;
for(let attempt=1;attempt<=4;attempt++){
  try{
    const result=await inspect();
    console.log('LIVE SEO AUDIT PASS '+JSON.stringify(result,null,2));
    process.exit(0);
  }catch(e){
    error=e;
    console.error('LIVE SEO AUDIT attempt '+attempt+': '+e.message);
    if(attempt<4)await sleep(15000);
  }
}
throw error;
