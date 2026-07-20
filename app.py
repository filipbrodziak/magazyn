from flask import Flask, render_template_string, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)

# ---------- BAZA DANYCH ----------
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///magazyn.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


# ---------- MODELE ----------
class Kategoria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nazwa = db.Column(db.String(100), unique=True, nullable=False)
    produkty = db.relationship("Produkt", backref="kategoria", lazy=True)


class Produkt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nazwa = db.Column(db.String(200), nullable=False)
    ilosc = db.Column(db.Integer, default=0)
    jednostka = db.Column(db.String(20), default="szt.")
    opis = db.Column(db.Text, default="")
    kategoria_id = db.Column(db.Integer, db.ForeignKey("kategoria.id"), nullable=False)
    data_dodania = db.Column(db.DateTime, default=datetime.utcnow)


class Historia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    produkt_id = db.Column(db.Integer, db.ForeignKey("produkt.id"), nullable=True)
    produkt_nazwa = db.Column(db.String(200), nullable=False)
    kategoria_nazwa = db.Column(db.String(100), nullable=False)
    zmiana = db.Column(db.Integer, nullable=False)
    stan_przed = db.Column(db.Integer, nullable=False)
    stan_po = db.Column(db.Integer, nullable=False)
    jednostka = db.Column(db.String(20), default="szt.")
    data = db.Column(db.DateTime, default=datetime.utcnow)
    cofnieta = db.Column(db.Boolean, default=False)


# ---------- STRONY ----------
@app.route("/")
def strona_glowna():
    sortuj = request.args.get("sortuj", "kategoria")
    szukaj = request.args.get("szukaj", "").strip()

    query = Produkt.query.join(Kategoria)

    if szukaj:
        query = query.filter(
            (Produkt.nazwa.ilike(f"%{szukaj}%")) |
            (Produkt.opis.ilike(f"%{szukaj}%")) |
            (Kategoria.nazwa.ilike(f"%{szukaj}%"))
        )

    if sortuj == "kategoria":
        query = query.order_by(Kategoria.nazwa, Produkt.nazwa)
    elif sortuj == "nazwa":
        query = query.order_by(Produkt.nazwa)
    elif sortuj == "ilosc":
        query = query.order_by(Produkt.ilosc)
    else:
        query = query.order_by(Kategoria.nazwa, Produkt.nazwa)

    produkty = query.all()
    kategorie = Kategoria.query.order_by(Kategoria.nazwa).all()

    return render_template_string(
        SZABLON,
        produkty=produkty,
        kategorie=kategorie,
        sortuj=sortuj,
        szukaj=szukaj
    )


@app.route("/dodaj", methods=["POST"])
def dodaj_produkt():
    nazwa = request.form["nazwa"].strip()
    ilosc = int(request.form["ilosc"])
    jednostka = request.form.get("jednostka", "szt.")
    opis = request.form.get("opis", "").strip()
    kategoria_id = int(request.form["kategoria_id"])
    kat = Kategoria.query.get(kategoria_id)

    istnieje = Produkt.query.filter_by(nazwa=nazwa, kategoria_id=kategoria_id).first()
    if istnieje:
        stan_przed = istnieje.ilosc
        istnieje.ilosc += ilosc
        stan_po = istnieje.ilosc
        produkt_id = istnieje.id
    else:
        stan_przed = 0
        nowy = Produkt(nazwa=nazwa, ilosc=ilosc, jednostka=jednostka, opis=opis, kategoria_id=kategoria_id)
        db.session.add(nowy)
        db.session.flush()
        stan_po = ilosc
        produkt_id = nowy.id

    wpis = Historia(
        produkt_id=produkt_id,
        produkt_nazwa=nazwa,
        kategoria_nazwa=kat.nazwa if kat else "—",
        zmiana=+ilosc,
        stan_przed=stan_przed,
        stan_po=stan_po,
        jednostka=jednostka
    )
    db.session.add(wpis)
    db.session.commit()

    return redirect(url_for("strona_glowna"))


@app.route("/usun/<int:id>")
def usun_produkt(id):
    produkt = Produkt.query.get(id)
    if produkt:
        kat = produkt.kategoria
        wpis = Historia(
            produkt_id=None,
            produkt_nazwa=produkt.nazwa,
            kategoria_nazwa=kat.nazwa if kat else "—",
            zmiana=-produkt.ilosc,
            stan_przed=produkt.ilosc,
            stan_po=0,
            jednostka=produkt.jednostka
        )
        db.session.add(wpis)
        db.session.delete(produkt)
        db.session.commit()
    return redirect(url_for("strona_glowna"))


@app.route("/zmien", methods=["POST"])
def zmien_ilosc():
    id = int(request.form["id"])
    akcja = request.form["akcja"]
    wartosc = int(request.form["wartosc"])

    produkt = Produkt.query.get(id)
    if produkt:
        kat = produkt.kategoria
        stan_przed = produkt.ilosc

        if akcja == "plus":
            produkt.ilosc += wartosc
            zmiana = +wartosc
        elif akcja == "minus":
            produkt.ilosc = max(0, produkt.ilosc - wartosc)
            zmiana = -wartosc

        stan_po = produkt.ilosc

        wpis = Historia(
            produkt_id=produkt.id,
            produkt_nazwa=produkt.nazwa,
            kategoria_nazwa=kat.nazwa if kat else "—",
            zmiana=zmiana,
            stan_przed=stan_przed,
            stan_po=stan_po,
            jednostka=produkt.jednostka
        )
        db.session.add(wpis)
        db.session.commit()

    return redirect(url_for("strona_glowna"))


@app.route("/historia")
def historia():
    wpisy = Historia.query.order_by(Historia.data.desc()).all()
    return render_template_string(SZABLON_HISTORIA, wpisy=wpisy)


@app.route("/cofnij/<int:id>")
def cofnij(id):
    wpis = Historia.query.get(id)
    if wpis and not wpis.cofnieta:
        if wpis.produkt_id:
            produkt = Produkt.query.get(wpis.produkt_id)
            if produkt:
                stan_przed_cofnieciem = produkt.ilosc
                produkt.ilosc -= wpis.zmiana
                produkt.ilosc = max(0, produkt.ilosc)
                stan_po_cofnieciu = produkt.ilosc

                cofniecie = Historia(
                    produkt_id=produkt.id,
                    produkt_nazwa=wpis.produkt_nazwa,
                    kategoria_nazwa=wpis.kategoria_nazwa,
                    zmiana=-wpis.zmiana,
                    stan_przed=stan_przed_cofnieciem,
                    stan_po=stan_po_cofnieciu,
                    jednostka=wpis.jednostka
                )
                db.session.add(cofniecie)

        wpis.cofnieta = True
        db.session.commit()

    return redirect(url_for("historia"))


@app.route("/kategorie")
def zarzadzaj_kategoriami():
    kategorie = Kategoria.query.order_by(Kategoria.nazwa).all()
    return render_template_string(SZABLON_KATEGORIE, kategorie=kategorie)


@app.route("/dodaj_kategorie", methods=["POST"])
def dodaj_kategorie():
    nazwa = request.form["nazwa"].strip()
    if nazwa and not Kategoria.query.filter_by(nazwa=nazwa).first():
        nowa = Kategoria(nazwa=nazwa)
        db.session.add(nowa)
        db.session.commit()
    return redirect(url_for("zarzadzaj_kategoriami"))


@app.route("/usun_kategorie/<int:id>")
def usun_kategorie(id):
    kat = Kategoria.query.get(id)
    if kat:
        Produkt.query.filter_by(kategoria_id=id).delete()
        db.session.delete(kat)
        db.session.commit()
    return redirect(url_for("zarzadzaj_kategoriami"))


# ---------- SZABLONY ----------
SZABLON = r"""
<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Magazyn Znakow Drogowych</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Segoe UI', Arial, sans-serif; max-width: 1200px; margin: 20px auto; padding: 0 15px; background: #f0f2f5; }
        h1 { color: #1a1a2e; margin-bottom: 5px; font-size: 26px; }
        .podtytul { color: #666; margin-bottom: 20px; font-size: 14px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }
        .btn-historia { background: #1a1a2e; color: white; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-weight: bold; font-size: 14px; }
        .btn-historia:hover { background: #2d2d4e; }
        form.dodaj-form { background: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.08); display: flex; flex-wrap: wrap; gap: 10px; align-items: end; }
        form.dodaj-form input, form.dodaj-form select { padding: 10px 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; }
        form.dodaj-form input[type="text"] { flex: 2; min-width: 180px; }
        form.dodaj-form input[type="number"] { width: 90px; }
        form.dodaj-form select { min-width: 140px; }
        form.dodaj-form button { padding: 10px 24px; background: #e67e22; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: bold; }
        form.dodaj-form button:hover { background: #d35400; }
        form.dodaj-form label { font-size: 12px; color: #888; display: block; margin-bottom: 3px; }
        .toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; flex-wrap: wrap; gap: 10px; }
        .toolbar-left { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
        .btn-outline { padding: 8px 16px; border: 2px solid #4a90d9; color: #4a90d9; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: bold; background: white; text-decoration: none; display: inline-block; }
        .btn-outline:hover { background: #4a90d9; color: white; }
        .btn-outline.aktywny { background: #4a90d9; color: white; }
        .szukaj-input { padding: 8px 14px; border: 2px solid #ddd; border-radius: 6px; font-size: 14px; width: 250px; transition: border 0.2s; }
        .szukaj-input:focus { outline: none; border-color: #4a90d9; }
        .licznik { font-size: 13px; color: #888; white-space: nowrap; }
        .tabela-wrapper { overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.08); min-width: 700px; }
        th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid #eee; }
        th { background: #1a1a2e; color: white; font-weight: 600; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; }
        tr:hover { background: #f8f9ff; }
        .kat-badge { display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 12px; font-weight: bold; white-space: nowrap; }
        .kat-A { background: #ffeaa7; color: #8b7000; }
        .kat-B { background: #dfe6e9; color: #2d3436; }
        .kat-D { background: #a29bfe; color: #3c2d8c; }
        .kat-inna { background: #fab1a0; color: #6b1d00; }
        .ilosc-niska { color: #e74c3c; font-weight: bold; }
        .ilosc-ok { color: #27ae60; }
        .przyciski { display: flex; gap: 5px; align-items: center; }
        .btn { padding: 6px 14px; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; text-decoration: none; display: inline-block; font-weight: bold; }
        .btn-zmiana { background: #ecf0f1; color: #2c3e50; }
        .btn-zmiana:hover { background: #d5dbdb; }
        .btn-usun { background: #e74c3c; color: white; }
        .btn-usun:hover { background: #c0392b; }
        .pusto { text-align: center; color: #999; padding: 40px; font-size: 16px; }
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 1000; justify-content: center; align-items: center; }
        .modal.aktywny { display: flex; }
        .modal-content { background: white; padding: 30px; border-radius: 12px; max-width: 460px; width: 90%; box-shadow: 0 10px 40px rgba(0,0,0,0.3); }
        .modal-content h3 { margin-bottom: 8px; color: #1a1a2e; }
        .modal-content p { margin-bottom: 12px; color: #555; font-size: 14px; }
        .modal-content .produkt-info { background: #f8f9fa; padding: 10px 14px; border-radius: 6px; margin-bottom: 15px; font-size: 14px; }
        .modal-content input { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 16px; text-align: center; margin-bottom: 15px; }
        .modal-buttons { display: flex; gap: 10px; justify-content: flex-end; }
        .modal-buttons button { padding: 10px 24px; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: bold; }
        .btn-potwierdz { background: #27ae60; color: white; }
        .btn-potwierdz:hover { background: #219a52; }
        .btn-potwierdz.odejmij { background: #e74c3c; }
        .btn-potwierdz.odejmij:hover { background: #c0392b; }
        .btn-anuluj { background: #bdc3c7; color: #2c3e50; }
        .btn-anuluj:hover { background: #a6acaf; }
        .podsumowanie { display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 14px; }
        .podsumowanie span { font-weight: bold; }
        .zmiana-plus { color: #27ae60; font-size: 18px; }
        .zmiana-minus { color: #e74c3c; font-size: 18px; }
        @media (max-width: 768px) {
            form.dodaj-form { flex-direction: column; }
            form.dodaj-form input, form.dodaj-form select { width: 100%; }
            .szukaj-input { width: 100%; }
            table { font-size: 13px; }
            th, td { padding: 8px 10px; }
        }
    </style>
</head>
<body>
    <h1>🚸 Magazyn Znakow Drogowych</h1>
    <div class="podtytul">
        <span>Zarzadzanie stanem magazynowym</span>
        <a href="/historia" class="btn-historia">📋 Historia zmian</a>
    </div>

    <form class="dodaj-form" action="/dodaj" method="POST">
        <div>
            <label>Nazwa znaku</label>
            <input type="text" name="nazwa" placeholder="np. A-7 (ustap pierwszenstwa)..." required>
        </div>
        <div>
            <label>Ilosc</label>
            <input type="number" name="ilosc" value="1" min="1" required>
        </div>
        <div>
            <label>Jednostka</label>
            <select name="jednostka">
                <option value="szt.">szt.</option>
                <option value="kpl.">kpl. (komplet)</option>
                <option value="m2">m2 (folia)</option>
            </select>
        </div>
        <div>
            <label>Kategoria</label>
            <select name="kategoria_id" required>
                {% for kat in kategorie %}
                <option value="{{ kat.id }}">{{ kat.nazwa }}</option>
                {% endfor %}
            </select>
        </div>
        <div>
            <label>Opis (opcjonalnie)</label>
            <input type="text" name="opis" placeholder="np. folia I gen., podklad...">
        </div>
        <button type="submit">➕ Dodaj</button>
    </form>

    <div class="toolbar">
        <div class="toolbar-left">
            <strong>Sortuj:</strong>
            <a href="?sortuj=kategoria&szukaj={{ szukaj }}" class="btn-outline {% if sortuj == 'kategoria' %}aktywny{% endif %}">📂 Kategoria</a>
            <a href="?sortuj=nazwa&szukaj={{ szukaj }}" class="btn-outline {% if sortuj == 'nazwa' %}aktywny{% endif %}">🔤 Nazwa</a>
            <a href="?sortuj=ilosc&szukaj={{ szukaj }}" class="btn-outline {% if sortuj == 'ilosc' %}aktywny{% endif %}">📊 Ilosc</a>
        </div>
        <div class="toolbar-left">
            <a href="/kategorie" class="btn-outline">⚙️ Kategorie</a>
        </div>
    </div>

    <div style="margin-bottom: 15px;">
        <input type="text" class="szukaj-input" id="szukajInput" placeholder="🔍 Szukaj produktu, kategorii lub opisu..." value="{{ szukaj }}" autocomplete="off">
        <span class="licznik" id="licznik">
            {% if szukaj %}
                Znaleziono: {{ produkty|length }} produkt(ow)
            {% else %}
                Lacznie: {{ produkty|length }} produkt(ow)
            {% endif %}
        </span>
    </div>

    {% if produkty %}
    <div class="tabela-wrapper">
    <table>
        <thead>
            <tr>
                <th>Znak</th>
                <th>Kategoria</th>
                <th>Ilosc</th>
                <th>Opis</th>
                <th>Akcje</th>
            </tr>
        </thead>
        <tbody>
            {% for p in produkty %}
            <tr>
                <td><strong>{{ p.nazwa }}</strong></td>
                <td>
                    {% set kat_klasa = 'kat-inna' %}
                    {% if 'A (' in p.kategoria.nazwa or p.kategoria.nazwa.startswith('Znaki A') %}{% set kat_klasa = 'kat-A' %}
                    {% elif 'B (' in p.kategoria.nazwa or p.kategoria.nazwa.startswith('Znaki B') %}{% set kat_klasa = 'kat-B' %}
                    {% elif 'D (' in p.kategoria.nazwa or p.kategoria.nazwa.startswith('Znaki D') %}{% set kat_klasa = 'kat-D' %}
                    {% endif %}
                    <span class="kat-badge {{ kat_klasa }}">{{ p.kategoria.nazwa }}</span>
                </td>
                <td>
                    <span class="{% if p.ilosc <= 5 %}ilosc-niska{% else %}ilosc-ok{% endif %}">
                        {{ p.ilosc }} {{ p.jednostka }}
                    </span>
                </td>
                <td>{{ p.opis }}</td>
                <td>
                    <div class="przyciski">
                        <button class="btn btn-zmiana" onclick="otworzModalKrok1({{ p.id }}, 'plus', '{{ p.nazwa }}', {{ p.ilosc }}, '{{ p.jednostka }}', '{{ p.kategoria.nazwa }}')">📥</button>
                        <button class="btn btn-zmiana" onclick="otworzModalKrok1({{ p.id }}, 'minus', '{{ p.nazwa }}', {{ p.ilosc }}, '{{ p.jednostka }}', '{{ p.kategoria.nazwa }}')">📤</button>
                        <a href="/usun/{{ p.id }}" class="btn btn-usun" onclick="return confirm('Na pewno usunac {{ p.nazwa }}?')">🗑</a>
                    </div>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    </div>
    {% else %}
    <p class="pusto">
        {% if szukaj %}
            🔍 Nic nie znaleziono dla "{{ szukaj }}"
        {% else %}
            📭 Magazyn jest pusty. Dodaj pierwszy znak powyzej!
        {% endif %}
    </p>
    {% endif %}

    <div class="modal" id="modalKrok1">
        <div class="modal-content">
            <h3 id="k1Tytul">Zmiana ilosci</h3>
            <div class="produkt-info" id="k1Info"></div>
            <input type="number" id="k1Wartosc" value="1" min="1" required>
            <div class="modal-buttons">
                <button class="btn-anuluj" onclick="zamknijWszystko()">Anuluj</button>
                <button class="btn-potwierdz" id="k1Dalej">Dalej →</button>
            </div>
        </div>
    </div>

    <div class="modal" id="modalKrok2">
        <div class="modal-content">
            <h3 id="k2Tytul">Potwierdz zmiane</h3>
            <div class="produkt-info" id="k2Info"></div>
            <div class="podsumowanie">
                <span>Stan przed:</span>
                <span id="k2Przed">0</span>
            </div>
            <div class="podsumowanie">
                <span>Zmiana:</span>
                <span id="k2Zmiana">0</span>
            </div>
            <div class="podsumowanie" style="border-top: 1px solid #eee; padding-top: 8px; margin-top: 5px;">
                <span>Stan po:</span>
                <span style="font-size: 18px; font-weight: bold;" id="k2Po">0</span>
            </div>
            <div class="modal-buttons" style="margin-top: 20px;">
                <button class="btn-anuluj" onclick="cofnijDoKroku1()">← Wstecz</button>
                <button class="btn-anuluj" onclick="zamknijWszystko()">Anuluj</button>
                <button class="btn-potwierdz" id="k2Zatwierdz">✅ Zatwierdz</button>
            </div>
        </div>
    </div>

    <form id="zmianaForm" action="/zmien" method="POST" style="display:none;">
        <input type="hidden" name="id" id="zmianaId">
        <input type="hidden" name="akcja" id="zmianaAkcja">
        <input type="hidden" name="wartosc" id="zmianaWartosc">
    </form>

    <script>
        var daneZmiany = {};

        function otworzModalKrok1(id, akcja, nazwa, ilosc, jednostka, kategoria) {
            daneZmiany = { id: id, akcja: akcja, nazwa: nazwa, ilosc: ilosc, jednostka: jednostka, kategoria: kategoria };
            var info = '<strong>' + nazwa + '</strong><br>Kategoria: ' + kategoria + '<br>Obecny stan: <strong>' + ilosc + ' ' + jednostka + '</strong>';
            document.getElementById('k1Info').innerHTML = info;
            document.getElementById('k1Wartosc').value = 1;
            if (akcja === 'plus') {
                document.getElementById('k1Tytul').textContent = '📥 Przyjecie na magazyn';
                document.getElementById('k1Dalej').className = 'btn-potwierdz';
                document.getElementById('k1Dalej').textContent = 'Dalej →';
            } else {
                document.getElementById('k1Tytul').textContent = '📤 Wydanie z magazynu';
                document.getElementById('k1Dalej').className = 'btn-potwierdz odejmij';
                document.getElementById('k1Dalej').textContent = 'Dalej →';
            }
            document.getElementById('modalKrok1').classList.add('aktywny');
            document.getElementById('k1Wartosc').focus();
            document.getElementById('k1Wartosc').select();
        }

        function przejdzDoKroku2() {
            var wartosc = parseInt(document.getElementById('k1Wartosc').value);
            if (isNaN(wartosc) || wartosc < 1) { alert('Wpisz poprawna ilosc (minimum 1)!'); return; }
            daneZmiany.wartosc = wartosc;
            var stanPrzed = daneZmiany.ilosc;
            var stanPo = (daneZmiany.akcja === 'plus') ? stanPrzed + wartosc : Math.max(0, stanPrzed - wartosc);
            var zmiana = (daneZmiany.akcja === 'plus') ? wartosc : -wartosc;
            document.getElementById('k2Info').innerHTML = '<strong>' + daneZmiany.nazwa + '</strong> | ' + daneZmiany.kategoria;
            document.getElementById('k2Przed').textContent = stanPrzed + ' ' + daneZmiany.jednostka;
            document.getElementById('k2Po').textContent = stanPo + ' ' + daneZmiany.jednostka;
            var zmianaEl = document.getElementById('k2Zmiana');
            if (zmiana > 0) {
                zmianaEl.innerHTML = '<span class="zmiana-plus">+' + zmiana + ' ' + daneZmiany.jednostka + '</span>';
            } else {
                zmianaEl.innerHTML = '<span class="zmiana-minus">' + zmiana + ' ' + daneZmiany.jednostka + '</span>';
            }
            if (daneZmiany.akcja === 'plus') {
                document.getElementById('k2Tytul').textContent = '📥 Potwierdz przyjecie';
                document.getElementById('k2Zatwierdz').className = 'btn-potwierdz';
                document.getElementById('k2Zatwierdz').textContent = '✅ Zatwierdz przyjecie';
            } else {
                document.getElementById('k2Tytul').textContent = '📤 Potwierdz wydanie';
                document.getElementById('k2Zatwierdz').className = 'btn-potwierdz odejmij';
                document.getElementById('k2Zatwierdz').textContent = '✅ Zatwierdz wydanie';
            }
            document.getElementById('modalKrok1').classList.remove('aktywny');
            document.getElementById('modalKrok2').classList.add('aktywny');
        }

        function cofnijDoKroku1() {
            document.getElementById('modalKrok2').classList.remove('aktywny');
            document.getElementById('modalKrok1').classList.add('aktywny');
            document.getElementById('k1Wartosc').focus();
            document.getElementById('k1Wartosc').select();
        }

        function zamknijWszystko() {
            document.getElementById('modalKrok1').classList.remove('aktywny');
            document.getElementById('modalKrok2').classList.remove('aktywny');
        }

        function zatwierdzZmiane() {
            document.getElementById('zmianaId').value = daneZmiany.id;
            document.getElementById('zmianaAkcja').value = daneZmiany.akcja;
            document.getElementById('zmianaWartosc').value = daneZmiany.wartosc;
            document.getElementById('zmianaForm').submit();
        }

        document.getElementById('k1Dalej').addEventListener('click', przejdzDoKroku2);
        document.getElementById('k2Zatwierdz').addEventListener('click', zatwierdzZmiane);
        document.getElementById('k1Wartosc').addEventListener('keydown', function(e) { if (e.key === 'Enter') { e.preventDefault(); przejdzDoKroku2(); } });
        document.getElementById('modalKrok1').addEventListener('click', function(e) { if (e.target === this) zamknijWszystko(); });
        document.getElementById('modalKrok2').addEventListener('click', function(e) { if (e.target === this) zamknijWszystko(); });

        var szukajTimeout;
        document.getElementById('szukajInput').addEventListener('input', function() {
            clearTimeout(szukajTimeout);
            var wartosc = this.value;
            szukajTimeout = setTimeout(function() {
                var url = new URL(window.location);
                if (wartosc) { url.searchParams.set('szukaj', wartosc); }
                else { url.searchParams.delete('szukaj'); }
                window.location = url.toString();
            }, 300);
        });

        document.addEventListener('keydown', function(e) {
            if ((e.ctrlKey || e.metaKey) && e.key === 'f') { e.preventDefault(); document.getElementById('szukajInput').focus(); }
        });
    </script>
</body>
</html>
"""

SZABLON_HISTORIA = r"""
<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Historia zmian - Magazyn Znakow</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Segoe UI', Arial, sans-serif; max-width: 1000px; margin: 30px auto; padding: 0 15px; background: #f0f2f5; }
        h1 { color: #1a1a2e; margin-bottom: 5px; }
        .podtytul { color: #666; margin-bottom: 20px; font-size: 14px; }
        .btn-powrot { display: inline-block; margin-bottom: 20px; color: #4a90d9; text-decoration: none; font-weight: bold; font-size: 14px; }
        .btn-powrot:hover { text-decoration: underline; }
        .wpis { background: white; border-radius: 10px; padding: 16px 20px; margin-bottom: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; border-left: 5px solid #ddd; }
        .wpis.przyjecie { border-left-color: #27ae60; }
        .wpis.wydanie { border-left-color: #e74c3c; }
        .wpis.usuniecie { border-left-color: #c0392b; background: #fff5f5; }
        .wpis.cofniety { opacity: 0.5; }
        .wpis.cofniety .wpis-lewy strong { text-decoration: line-through; }
        .wpis-lewy { flex: 1; min-width: 200px; }
        .wpis-lewy strong { font-size: 15px; color: #1a1a2e; }
        .wpis-lewy .meta { font-size: 12px; color: #999; margin-top: 2px; }
        .wpis-lewy .kat { font-size: 12px; color: #666; }
        .wpis-srodek { text-align: center; min-width: 120px; }
        .zmiana-ilosc { font-size: 20px; font-weight: bold; }
        .zmiana-plus { color: #27ae60; }
        .zmiana-minus { color: #e74c3c; }
        .wpis-prawy { text-align: right; min-width: 120px; }
        .stan { font-size: 13px; color: #555; }
        .stan span { font-weight: bold; }
        .btn-cofnij { background: #6c5ce7; color: white; padding: 7px 16px; border-radius: 4px; text-decoration: none; font-size: 13px; font-weight: bold; white-space: nowrap; }
        .btn-cofnij:hover { background: #5a4bd1; }
        .pusto { text-align: center; color: #999; padding: 40px; font-size: 16px; }
        .data-naglowek { color: #888; font-size: 13px; font-weight: bold; margin: 20px 0 10px 0; padding-bottom: 5px; border-bottom: 1px solid #ddd; }
        @media (max-width: 768px) {
            .wpis { flex-direction: column; align-items: flex-start; }
            .wpis-prawy { text-align: left; }
        }
    </style>
</head>
<body>
    <h1>📋 Historia zmian</h1>
    <p class="podtytul">Wszystkie operacje magazynowe — od najnowszych</p>
    <a href="/" class="btn-powrot">← Powrot do magazynu</a>

    {% if wpisy %}
        {% set ns = namespace(data='') %}
        {% for w in wpisy %}
            {% set dd = w.data.strftime('%Y-%m-%d') %}
            {% if dd != ns.data %}
                {% set ns.data = dd %}
                <div class="data-naglowek">📅 {{ w.data.strftime('%d.%m.%Y') }}</div>
            {% endif %}

            {% set klasa = 'przyjecie' if w.zmiana > 0 else 'wydanie' %}
            {% if w.produkt_id is none and w.zmiana < 0 %}{% set klasa = 'usuniecie' %}{% endif %}

            <div class="wpis {{ klasa }} {% if w.cofnieta %}cofniety{% endif %}">
                <div class="wpis-lewy">
                    <strong>{{ w.produkt_nazwa }}</strong>
                    {% if w.cofnieta %}<span style="color:#e74c3c; font-size:11px;">(COFNIETA)</span>{% endif %}
                    <div class="kat">{{ w.kategoria_nazwa }}</div>
                    <div class="meta">{{ w.data.strftime('%H:%M:%S') }}</div>
                </div>
                <div class="wpis-srodek">
                    <div class="zmiana-ilosc">
                        {% if w.zmiana > 0 %}
                            <span class="zmiana-plus">+{{ w.zmiana }} {{ w.jednostka }}</span>
                        {% else %}
                            <span class="zmiana-minus">{{ w.zmiana }} {{ w.jednostka }}</span>
                        {% endif %}
                    </div>
                </div>
                <div class="wpis-prawy">
                    <div class="stan">{{ w.stan_przed }} → <span>{{ w.stan_po }}</span> {{ w.jednostka }}</div>
                    {% if not w.cofnieta and w.produkt_id %}
                    <a href="/cofnij/{{ w.id }}" class="btn-cofnij" onclick="return confirm('Cofnac te zmiane?\\nStan wroci do {{ w.stan_przed }} {{ w.jednostka }}.')">↩ Cofnij</a>
                    {% endif %}
                </div>
            </div>
        {% endfor %}
    {% else %}
        <p class="pusto">📭 Brak wpisow w historii.</p>
    {% endif %}
</body>
</html>
"""

SZABLON_KATEGORIE = r"""
<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kategorie - Magazyn Znakow</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Segoe UI', Arial, sans-serif; max-width: 700px; margin: 30px auto; padding: 0 15px; background: #f0f2f5; }
        h1 { color: #1a1a2e; margin-bottom: 20px; }
        form { background: white; padding: 20px; border-radius: 10px; margin-bottom: 25px; box-shadow: 0 2px 10px rgba(0,0,0,0.08); display: flex; gap: 10px; }
        form input { flex: 1; padding: 10px 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; }
        form button { padding: 10px 20px; background: #e67e22; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; }
        form button:hover { background: #d35400; }
        ul { list-style: none; background: white; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.08); overflow: hidden; }
        li { padding: 15px 20px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; }
        li:last-child { border-bottom: none; }
        .btn-usun { background: #e74c3c; color: white; padding: 6px 14px; border-radius: 4px; text-decoration: none; font-size: 13px; font-weight: bold; }
        .btn-usun:hover { background: #c0392b; }
        .btn-powrot { display: inline-block; margin-top: 15px; color: #4a90d9; text-decoration: none; font-weight: bold; }
        .info { font-size: 13px; color: #888; margin-top: 5px; }
    </style>
</head>
<body>
    <h1>⚙️ Zarzadzanie kategoriami</h1>

    <form action="/dodaj_kategorie" method="POST">
        <input type="text" name="nazwa" placeholder="Nazwa kategorii (np. Znaki C)..." required>
        <button type="submit">➕ Dodaj</button>
    </form>

    {% if kategorie %}
    <ul>
        {% for kat in kategorie %}
        <li>
            <span><strong>{{ kat.nazwa }}</strong> <span class="info">({{ kat.produkty|length }} produktow)</span></span>
            <a href="/usun_kategorie/{{ kat.id }}" class="btn-usun" onclick="return confirm('Usuniecie kategorii usunie tez wszystkie znaki w niej! Kontynuowac?')">🗑 Usun</a>
        </li>
        {% endfor %}
    </ul>
    {% else %}
    <p style="color:#999; text-align:center; padding:30px;">Brak kategorii. Dodaj pierwsza!</p>
    {% endif %}

    <a href="/" class="btn-powrot">← Powrot do magazynu</a>
</body>
</html>
"""


# ---------- START ----------
# Tworzenie bazy przy starcie (Render)
with app.app_context():
    db.create_all()
    if not Kategoria.query.first():
        for nazwa in ["Znaki A (ostrzegawcze)", "Znaki B (nakazu)", "Znaki D (informacyjne)"]:
            db.session.add(Kategoria(nazwa=nazwa))
        db.session.commit()

# Tylko lokalnie
if __name__ == "__main__":
    app.run(debug=True)