/* The test site's shop (tests/site/site_server.py): AgentCake's demo shop until D37, now a test fixture.
   Everything runs in this page; the cart lives in localStorage. Nothing is sent anywhere except what
   cake's own page script records (inputs masked by cake's setting; card fields are never recorded).
   The look is shop.css beside it; COLORS are the products' own colours. */
(function () {
  var COLORS = { White: '#f3f1ec', Black: '#2b2b2b', Blue: '#2f6fd6', Red: '#c8372d', Navy: '#1f2f5c', Grey: '#9a9a9a',
    Olive: '#6b7040', Yellow: '#e8c22e', Sand: '#d8c49a', Brown: '#7a4b2a', Green: '#3f8a4f' };
  var CLOTHES = ['XS', 'S', 'M', 'L', 'XL'];
  var P = [
    { id: 'tote', name: 'Canvas Tote Bag', cat: 'Accessories', price: 18, colors: ['Sand', 'Black'], sizes: null, blurb: 'Heavy cotton canvas, inside pocket.' },
    { id: 'beanie', name: 'Wool Beanie', cat: 'Accessories', price: 22, colors: ['Grey', 'Navy', 'Red'], sizes: null, blurb: 'Soft merino rib knit.' },
    { id: 'linen-shirt', name: 'Linen Shirt', cat: 'Tops', price: 48, colors: ['White', 'Blue'], sizes: CLOTHES, blurb: 'Long sleeves, relaxed fit. Not a T-shirt.' },
    { id: 'socks', name: 'Running Socks (3-pack)', cat: 'Accessories', price: 14, colors: ['White', 'Black'], sizes: ['S', 'M', 'L'], blurb: 'Cushioned sole, breathable.' },
    { id: 'hoodie', name: 'Hooded Sweatshirt', cat: 'Tops', price: 55, colors: ['Grey', 'Navy', 'Olive'], sizes: CLOTHES, blurb: 'Brushed fleece inside.' },
    { id: 'denim-jacket', name: 'Denim Jacket', cat: 'Outerwear', price: 89, colors: ['Blue'], sizes: CLOTHES, blurb: 'Classic trucker cut.' },
    { id: 'classic-tee', name: 'Classic T-shirt', cat: 'Tops', price: 20, colors: ['White', 'Black', 'Blue', 'Red'], sizes: CLOTHES, blurb: 'Organic cotton crew neck T-shirt.' },
    { id: 'rain-jacket', name: 'Rain Jacket', cat: 'Outerwear', price: 95, colors: ['Yellow', 'Navy'], sizes: CLOTHES, blurb: 'Waterproof, packs into its pocket.' },
    { id: 'cap', name: 'Baseball Cap', cat: 'Accessories', price: 19, colors: ['Navy', 'Sand'], sizes: null, blurb: 'Adjustable strap.' },
    { id: 'shorts', name: 'Cargo Shorts', cat: 'Bottoms', price: 38, colors: ['Sand', 'Olive'], sizes: CLOTHES, blurb: 'Six pockets.' },
    { id: 'scarf', name: 'Knit Scarf', cat: 'Accessories', price: 27, colors: ['Red', 'Grey'], sizes: null, blurb: 'Chunky knit, 180 cm.' },
    { id: 'chinos', name: 'Slim Chinos', cat: 'Bottoms', price: 52, colors: ['Sand', 'Navy', 'Black'], sizes: CLOTHES, blurb: 'Stretch cotton twill.' },
    { id: 'kids-tee', name: "Kids' T-shirt", cat: 'Tops', price: 14, colors: ['Blue', 'Yellow'], sizes: ['4Y', '6Y', '8Y', '10Y'], blurb: 'Children’s sizes only.' },
    { id: 'belt', name: 'Leather Belt', cat: 'Accessories', price: 34, colors: ['Brown', 'Black'], sizes: ['S', 'M', 'L'], blurb: 'Full-grain leather.' },
    { id: 'bottle', name: 'Water Bottle', cat: 'Accessories', price: 16, colors: ['Green', 'White'], sizes: null, blurb: 'Steel, 750 ml.' }
  ];
  var PER_PAGE = 6;
  var app = document.getElementById('app');
  var page = document.body.getAttribute('data-page');
  var productName = document.body.getAttribute('data-product'); // Agent Cake's name, from data/product.json (shop.py)
  var qs = new URLSearchParams(location.search);

  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function money(n) { return '$' + n.toFixed(2); }
  function byId(id) { for (var i = 0; i < P.length; i++) if (P[i].id === id) return P[i]; return null; }
  function load(k, d) { try { var v = JSON.parse(localStorage.getItem(k)); return v == null ? d : v; } catch (e) { return d; } }
  function save(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  function cart() { return load('cake_demo_cart', []); }
  function setCart(c) { save('cake_demo_cart', c); count(); }
  function count() { var n = 0; cart().forEach(function (l) { n += l.qty; }); var el = document.getElementById('cartcount'); if (el) el.textContent = n; }
  function shirt(color) {
    var c = COLORS[color] || COLORS.Grey;
    // the background and the outline come from shop.css (tokens); only the product's colour is set here
    return '<svg class="swatch" viewBox="0 0 160 120" aria-hidden="true"><rect width="160" height="120"/>' +
      '<path d="M55 22 L70 16 Q80 26 90 16 L105 22 L122 40 L110 50 L104 44 L104 104 L56 104 L56 44 L50 50 L38 40 Z" fill="' + c + '"/></svg>';
  }

  function home() {
    var q = (qs.get('q') || '').trim(), cat = qs.get('cat') || '', sort = qs.get('sort') || 'featured';
    var pg = Math.max(1, parseInt(qs.get('page') || '1', 10) || 1);
    document.getElementById('q').value = q;
    var list = P.filter(function (p) {
      var hay = (p.name + ' ' + p.cat + ' ' + p.colors.join(' ') + ' ' + p.blurb).toLowerCase();
      return (!cat || p.cat === cat) && (!q || q.toLowerCase().split(/\s+/).every(function (w) { return hay.indexOf(w) >= 0 || hay.indexOf(w.replace(/s$/, '')) >= 0; }));
    });
    if (sort === 'price-asc') list.sort(function (a, b) { return a.price - b.price; });
    if (sort === 'price-desc') list.sort(function (a, b) { return b.price - a.price; });
    if (sort === 'name') list.sort(function (a, b) { return a.name.localeCompare(b.name); });
    var pages = Math.max(1, Math.ceil(list.length / PER_PAGE)); pg = Math.min(pg, pages);
    var shown = list.slice((pg - 1) * PER_PAGE, pg * PER_PAGE);
    function link(over) {
      var p = new URLSearchParams({ q: q, cat: cat, sort: sort, page: String(pg) });
      for (var k in over) p.set(k, over[k]);
      ['q', 'cat'].forEach(function (k) { if (!p.get(k)) p.delete(k); }); if (p.get('sort') === 'featured') p.delete('sort'); if (p.get('page') === '1') p.delete('page');
      var s = p.toString(); return '/demo' + (s ? '?' + s : '');
    }
    var cats = ['', 'Tops', 'Bottoms', 'Outerwear', 'Accessories'];
    var h = '<h1>' + (q ? 'Results for “' + esc(q) + '”' : 'All products') + '</h1>' +
      '<div class="filters"><div><label for="cat">Category</label><select id="cat">' +
      cats.map(function (c) { return '<option value="' + c + '"' + (c === cat ? ' selected' : '') + '>' + (c || 'All categories') + '</option>'; }).join('') +
      '</select></div><div><label for="sort">Sort by</label><select id="sort">' +
      [['featured', 'Featured'], ['price-asc', 'Price: low to high'], ['price-desc', 'Price: high to low'], ['name', 'Name']].map(function (o) { return '<option value="' + o[0] + '"' + (o[0] === sort ? ' selected' : '') + '>' + o[1] + '</option>'; }).join('') +
      '</select></div><div class="mut" style="font-size:13px">' + list.length + ' product' + (list.length === 1 ? '' : 's') + ' · page ' + pg + ' of ' + pages + '</div></div>';
    if (!shown.length) h += '<p>No products match. <a href="/demo">Show all products</a></p>';
    h += '<div class="grid">' + shown.map(function (p) {
      return '<div class="card"><a href="/demo/product?id=' + p.id + '" aria-hidden="true" tabindex="-1">' + shirt(p.colors[0]) + '</a><div class="body"><h3><a href="/demo/product?id=' + p.id + '">' + esc(p.name) + '</a></h3>' +
        '<div class="price">' + money(p.price) + '</div><div class="mut">' + esc(p.cat) + ' · ' + p.colors.length + ' colour' + (p.colors.length > 1 ? 's' : '') + ': ' + esc(p.colors.join(', ')) + '</div>' +
        '<a class="more" href="/demo/product?id=' + p.id + '">View product</a></div></div>';
    }).join('') + '</div>';
    if (pages > 1) {
      h += '<nav class="pager" aria-label="Pages">' + (pg > 1 ? '<a href="' + link({ page: String(pg - 1) }) + '">Previous</a>' : '');
      for (var i = 1; i <= pages; i++) h += i === pg ? '<span class="cur" aria-current="page">' + i + '</span>' : '<a href="' + link({ page: String(i) }) + '">' + i + '</a>';
      h += (pg < pages ? '<a href="' + link({ page: String(pg + 1) }) + '">Next</a>' : '') + '</nav>';
    }
    app.innerHTML = h;
    document.getElementById('cat').onchange = function () { location.href = link({ cat: this.value, page: '1' }); };
    document.getElementById('sort').onchange = function () { location.href = link({ sort: this.value, page: '1' }); };
  }

  function product() {
    var p = byId(qs.get('id'));
    if (!p) { app.innerHTML = '<h1>Product not found</h1><p><a href="/demo">Back to all products</a></p>'; return; }
    var reviews = [['Ana', 5, 'Fits as expected, colour is true to the photo.'], ['Marc', 4, 'Good quality. I sized up for a looser fit.'],
      ['Jun', 5, 'Bought two. Washes well.'], ['Priya', 3, 'Nice, but delivery took a while (it is a demo, so of course it did).'],
      ['Leo', 4, 'Exactly what I needed.']];
    var h = '<p><a href="/demo">← All products</a></p><div class="product"><div class="img" id="img">' + shirt(p.colors[0]) + '</div><div>' +
      '<h1 style="margin-top:0">' + esc(p.name) + '</h1><div class="price" style="font-size:20px">' + money(p.price) + '</div><p class="mut">' + esc(p.blurb) + '</p>' +
      '<div class="opts"><div><div class="mut" style="font-size:13px;margin-bottom:6px">Colour</div><div class="colors" role="radiogroup" aria-label="Colour">' +
      p.colors.map(function (c, i) { return '<label><input type="radio" name="color" value="' + c + '"' + (i === 0 ? ' checked' : '') + '><i style="background:' + COLORS[c] + '"></i>' + c + '</label>'; }).join('') + '</div></div>' +
      '<div class="row">' + (p.sizes ? '<div><label for="size" class="mut" style="font-size:13px">Size</label><select id="size"><option value="">Choose a size</option>' +
        p.sizes.map(function (s) { return '<option>' + s + '</option>'; }).join('') + '</select></div>' : '<div class="mut" style="font-size:13px">One size</div>') +
      '<div style="flex:0 0 100px"><label for="qty" class="mut" style="font-size:13px">Quantity</label><input id="qty" type="number" min="1" max="9" value="1"></div></div>' +
      '<div><button id="add" type="button">Add to cart</button> <a href="/demo/cart" style="margin-left:10px">View cart</a></div><div class="msg" id="msg" role="status"></div></div>' +
      (p.sizes && p.sizes[0] === 'XS' ? '<details><summary>Size guide</summary><div class="tablewrap"><table><tr><th>Size</th><th>Chest (cm)</th><th>Length (cm)</th></tr>' +
        [['XS', 86, 66], ['S', 92, 69], ['M', 98, 72], ['L', 104, 75], ['XL', 110, 78]].map(function (r) { return '<tr><td>' + r[0] + '</td><td>' + r[1] + '</td><td>' + r[2] + '</td></tr>'; }).join('') +
        '</table></div></details>' : '') + '</div></div>' +
      '<section class="reviews"><h2>Reviews (' + reviews.length + ')</h2>' + reviews.map(function (r) {
        return '<div class="review"><b>' + r[0] + '</b> <span class="stars" aria-label="' + r[1] + ' of 5">' + '★'.repeat(r[1]) + '☆'.repeat(5 - r[1]) + '</span><p>' + esc(r[2]) + '</p></div>';
      }).join('') + '</section><section><h2>You may also like</h2><div class="grid">' +
      P.filter(function (o) { return o.id !== p.id && o.cat === p.cat; }).slice(0, 3).map(function (o) {
        return '<div class="card">' + shirt(o.colors[0]) + '<div class="body"><h3><a href="/demo/product?id=' + o.id + '">' + esc(o.name) + '</a></h3><div class="price">' + money(o.price) + '</div></div></div>';
      }).join('') + '</div></section>';
    app.innerHTML = h;
    Array.prototype.forEach.call(document.querySelectorAll('input[name=color]'), function (r) {
      r.onchange = function () { document.getElementById('img').innerHTML = shirt(this.value); };
    });
    document.getElementById('add').onclick = function () {
      var msg = document.getElementById('msg'), sizeEl = document.getElementById('size');
      var size = sizeEl ? sizeEl.value : 'One size';
      var color = (document.querySelector('input[name=color]:checked') || {}).value;
      var qty = Math.max(1, Math.min(9, parseInt(document.getElementById('qty').value, 10) || 1));
      if (!size) { msg.className = 'msg bad'; msg.textContent = 'Please choose a size first.'; if (sizeEl) sizeEl.focus(); return; }
      var c = cart(), found = false;
      c.forEach(function (l) { if (l.id === p.id && l.color === color && l.size === size) { l.qty = Math.min(9, l.qty + qty); found = true; } });
      if (!found) c.push({ id: p.id, color: color, size: size, qty: qty });
      setCart(c);
      msg.className = 'msg ok'; msg.innerHTML = 'Added ' + qty + ' × ' + esc(p.name) + ' (' + esc(color) + ', ' + esc(size) + ') to your cart. <a href="/demo/cart">Go to cart</a>';
    };
  }

  function totals(c, express, promo) {
    var sub = 0; c.forEach(function (l) { var p = byId(l.id); if (p) sub += p.price * l.qty; });
    var disc = promo ? Math.round(sub * 10) / 100 : 0, ship = express ? 8 : 0;
    return { sub: sub, disc: disc, ship: ship, total: sub - disc + ship };
  }

  function cartPage() {
    var c = cart(), promo = load('cake_demo_promo', false);
    if (!c.length) { app.innerHTML = '<h1>Your cart</h1><p>Your cart is empty. <a href="/demo">Browse products</a></p>'; return; }
    var t = totals(c, false, promo);
    app.innerHTML = '<h1>Your cart</h1><div class="tablewrap"><table><tr><th>Product</th><th>Colour</th><th>Size</th><th>Qty</th><th>Price</th><th></th></tr>' +
      c.map(function (l, i) {
        var p = byId(l.id) || { name: l.id, price: 0 };
        return '<tr class="cartrow"><td><a href="/demo/product?id=' + l.id + '">' + esc(p.name) + '</a></td><td>' + esc(l.color) + '</td><td>' + esc(l.size) + '</td>' +
          '<td><input type="number" min="1" max="9" value="' + l.qty + '" data-i="' + i + '" aria-label="Quantity"></td><td>' + money(p.price * l.qty) + '</td>' +
          '<td><button class="ghost" type="button" data-rm="' + i + '">Remove</button></td></tr>';
      }).join('') + '</table></div>' +
      '<div class="row" style="max-width:420px;margin-top:16px"><div><label for="promo" class="mut" style="font-size:13px">Promo code</label><input id="promo" type="text" placeholder="Try DEMO10"></div><div style="flex:0 0 auto"><button class="ghost" id="apply" type="button">Apply</button></div></div>' +
      '<div class="msg" id="pmsg" role="status">' + (promo ? 'DEMO10 applied: 10% off.' : '') + '</div>' +
      '<div class="totals"><div><span>Subtotal</span><span>' + money(t.sub) + '</span></div>' + (promo ? '<div><span>Discount</span><span>−' + money(t.disc) + '</span></div>' : '') +
      '<div><span>Shipping</span><span>chosen at checkout</span></div><div class="grand"><span>Total</span><span>' + money(t.total) + '</span></div>' +
      '<p style="text-align:right"><a class="btn" href="/demo/checkout" id="checkout">Checkout</a></p></div>';
    Array.prototype.forEach.call(app.querySelectorAll('input[data-i]'), function (el) {
      el.onchange = function () { var c2 = cart(); c2[+this.getAttribute('data-i')].qty = Math.max(1, Math.min(9, parseInt(this.value, 10) || 1)); setCart(c2); cartPage(); };
    });
    Array.prototype.forEach.call(app.querySelectorAll('button[data-rm]'), function (el) {
      el.onclick = function () { var c2 = cart(); c2.splice(+this.getAttribute('data-rm'), 1); setCart(c2); cartPage(); };
    });
    document.getElementById('apply').onclick = function () {
      var ok = document.getElementById('promo').value.trim().toUpperCase() === 'DEMO10';
      if (ok) { save('cake_demo_promo', true); cartPage(); } else { var m = document.getElementById('pmsg'); m.className = 'msg bad'; m.textContent = 'That code is not valid.'; }
    };
  }

  function checkout() {
    var c = cart(), promo = load('cake_demo_promo', false);
    if (!c.length) { app.innerHTML = '<h1>Checkout</h1><p>Your cart is empty. <a href="/demo">Browse products</a></p>'; return; }
    function f(id, label, type, extra) { return '<label for="' + id + '">' + label + '</label><input id="' + id + '" name="' + id + '" type="' + (type || 'text') + '" required ' + (extra || '') + '>'; }
    var countries = ['', 'United States', 'Canada', 'United Kingdom', 'Germany', 'France', 'Japan', 'Australia', 'Other'];
    app.innerHTML = '<h1>Checkout</h1><p class="mut">Demo checkout: use made-up details. Nothing is charged, shipped or stored; card fields are never recorded by ' + esc(productName) + '.</p>' +
      '<form class="checkout" id="form" novalidate><div>' +
      '<fieldset><legend>Contact</legend>' + f('email', 'Email', 'email', 'autocomplete="off" placeholder="Email"') + '</fieldset>' +
      '<fieldset><legend>Shipping address</legend>' + f('fullname', 'Full name', 'text', 'autocomplete="off"') + f('address', 'Street address', 'text', 'autocomplete="off"') +
      '<div class="row"><div>' + f('city', 'City', 'text', 'autocomplete="off"') + '</div><div>' + f('postcode', 'Postcode', 'text', 'autocomplete="off"') + '</div></div>' +
      '<label for="country">Country</label><select id="country" name="country" required>' + countries.map(function (c) { return '<option value="' + c + '">' + (c || 'Choose a country') + '</option>'; }).join('') + '</select></fieldset>' +
      '<fieldset><legend>Delivery</legend><label class="inline"><input type="radio" name="ship" value="standard" checked> Standard, 5–7 days, free</label>' +
      '<label class="inline"><input type="radio" name="ship" value="express"> Express, 1–2 days, $8.00</label></fieldset>' +
      '<fieldset><legend>Payment (demo)</legend><p class="mut" style="font-size:13px;margin:0">Any made-up card number works.</p>' +
      f('cardname', 'Name on card', 'text', 'autocomplete="off"') + f('cardnumber', 'Card number', 'text', 'inputmode="numeric" autocomplete="off" data-cake-private placeholder="4242 4242 4242 4242"') +
      '<div class="row"><div>' + f('expiry', 'Expiry (MM/YY)', 'text', 'autocomplete="off" data-cake-private placeholder="12/29"') + '</div><div>' + f('cvc', 'CVC', 'text', 'inputmode="numeric" autocomplete="off" data-cake-private placeholder="123"') + '</div></div></fieldset>' +
      '<label class="inline"><input type="checkbox" id="agree" required> I understand this is a demo and no real order is placed.</label>' +
      '<div class="msg bad" id="err" role="alert"></div><p><button type="submit" id="place">Place order</button></p></div>' +
      '<aside class="summary" id="summary"></aside></form>';
    function summary() {
      var express = document.querySelector('input[name=ship]:checked').value === 'express', t = totals(c, express, promo);
      document.getElementById('summary').innerHTML = '<h2 style="margin-top:0;font-size:17px">Order summary</h2>' + c.map(function (l) {
        var p = byId(l.id) || { name: l.id, price: 0 }; return '<div class="totals" style="max-width:none;margin:0"><div><span>' + l.qty + ' × ' + esc(p.name) + ' (' + esc(l.color) + ', ' + esc(l.size) + ')</span><span>' + money(p.price * l.qty) + '</span></div></div>';
      }).join('') + '<div class="totals" style="max-width:none"><div><span>Subtotal</span><span>' + money(t.sub) + '</span></div>' + (promo ? '<div><span>Discount</span><span>−' + money(t.disc) + '</span></div>' : '') +
        '<div><span>Shipping</span><span>' + (t.ship ? money(t.ship) : 'Free') + '</span></div><div class="grand"><span>Total</span><span>' + money(t.total) + '</span></div></div>';
      return t;
    }
    summary();
    Array.prototype.forEach.call(document.querySelectorAll('input[name=ship]'), function (r) { r.onchange = summary; });
    document.getElementById('form').onsubmit = function (e) {
      e.preventDefault();
      var err = document.getElementById('err'), bad = [];
      ['email', 'fullname', 'address', 'city', 'postcode', 'country', 'cardname', 'cardnumber', 'expiry', 'cvc'].forEach(function (id) {
        var el = document.getElementById(id); if (!el.value.trim()) bad.push(el.labels && el.labels[0] ? el.labels[0].textContent : id);
      });
      var digits = document.getElementById('cardnumber').value.replace(/\D/g, '');
      if (document.getElementById('cardnumber').value.trim() && (digits.length < 12 || digits.length > 19)) bad.push('Card number (12–19 digits)');
      if (document.getElementById('email').value.trim() && document.getElementById('email').value.indexOf('@') < 1) bad.push('Email (needs an @)');
      if (!document.getElementById('agree').checked) bad.push('the demo checkbox');
      if (bad.length) { err.textContent = 'Please fill in: ' + bad.join(', ') + '.'; return; }
      var t = summary(), n = 0; c.forEach(function (l) { n += l.qty; });
      // Keep only the order summary. Form values (name, address, card) are not saved anywhere.
      save('cake_demo_last_order', { code: 'DEMO-' + Math.random().toString(36).slice(2, 7).toUpperCase(), items: n, total: t.total,
        lines: c.map(function (l) { var p = byId(l.id); return (p ? p.name : l.id) + ' (' + l.color + ', ' + l.size + ') × ' + l.qty; }) });
      document.getElementById('form').reset();
      setCart([]); save('cake_demo_promo', false);
      location.href = '/demo/done';
    };
  }

  function done() {
    var o = load('cake_demo_last_order', null);
    app.innerHTML = o ? '<div class="done"><p class="mut">Demo order placed</p><div class="code" id="order-code">' + esc(o.code) + '</div><p>' + o.lines.map(esc).join('<br>') + '</p><p>Total ' + money(o.total) +
      '</p><p class="mut">This is the ' + esc(productName) + ' demo shop. Nothing was ordered, charged or shipped.</p><p><a href="/demo">Back to the shop</a> · <a href="/">See this visit in ' + esc(productName) + '</a></p></div>'
      : '<div class="done"><p>No demo order yet.</p><p><a href="/demo">Go to the shop</a></p></div>';
  }

  count();
  ({ home: home, product: product, cart: cartPage, checkout: checkout, done: done }[page] || home)();
})();
