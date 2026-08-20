const fs = require('fs');
const jsdom = require('jsdom');
const { JSDOM } = jsdom;

const html = fs.readFileSync('frontend/dashboard.html', 'utf8');

const dom = new JSDOM(html, {
    url: 'http://localhost/dashboard.html',
    runScripts: 'dangerously',
    virtualConsole: new jsdom.VirtualConsole().sendTo(console)
});

setTimeout(() => {
    console.log("DOM parsed. Sidebar email:", dom.window.document.getElementById('sidebar-email').textContent);
    console.log("Table status:", dom.window.document.getElementById('monitors-tbody').innerHTML.substring(0, 50));
    console.log("Total body length:", dom.window.document.body.innerHTML.length);
}, 1000);
