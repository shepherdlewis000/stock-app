import os

from sql import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
import datetime
from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    # disable caching of responses provided we're in debugging mode
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter - usd is function in helpers.py
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    rows = db.execute("SELECT * FROM holdings WHERE user_id = :user_id", user_id=session["user_id"])

    rows2 = db.execute("SELECT * FROM users where id = :user_id", user_id=session['user_id'])
    cash = rows2[0]["cash"]
    table = "<table class='table'><thead><tr><th>Stock</th><th>Shares</th><th>Current price</th><th>Value</th></tr></thead><tbody>"
    totalValue = 0
    for row in rows:
        #symbol = row[0]["symbol"]
        #symbol = rows[row]["symbol"]
        symbol = row["symbol"]
        #shares = row[0]["shares"]
        shares = row["shares"]
        stock = lookup(symbol)
        price = stock["price"] # the current price
        value = price * shares
        table = table + "<tr><td>" + symbol + "</td><td>" + str(shares) + "</td><td>" + str(usd(price)) + "</td><td>" + str(usd(value)) + "</td></tr>"
        totalValue = totalValue + value

    totalWorth = cash + totalValue
    table = table + "</tbody><tfoot><tr><td></td><td></td><td>Total stock value</td><td>" + str(usd(totalValue)) + "</td></tr>"
    table = table + "<tr><td></td><td></td><td>Total cash on hand</td><td>" + str(usd(cash)) + "</td></tr>"
    table = table + "<tr><td></td><td></td><td>Total worth (cash & stocks)</td><td>" + str(usd(totalWorth)) + "</td></tr></tfoot></table>"
    # return apology("TODO from /")
    return render_template("index.html", table=table)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == 'GET':
        return render_template("buy.html")

    # check if valid input
    stock = lookup(request.form.get("symbol"))
    if not stock:
        return apology("Could not find that symbol", 400)
    shares = request.form.get("shares")
    if not shares:
        return apology("Missing no. of shares", 400)


    shares = request.form.get("shares")

    rows = db.execute("SELECT * FROM users where id = :user_id", user_id=session['user_id'])
    cash = rows[0]["cash"]
    price = stock["price"]

    try:
        shares = int(shares)
    except ValueError:
        return apology("Shares must be an integer.", 400)

    if not shares > 0:
        return apology("Shares must be greater than zero", 400)

    cost = shares * price

    if cash < cost:
        return apology("Not enough money :-(", 403)

    typetrans = 'buy'
    symbol = stock['symbol']
    user_id = session['user_id']

    db.execute("INSERT INTO transactions('userid', 'type', 'symbol', 'shares', 'price') VALUES (:userid, :type, :symbol, :shares, :price)", userid=user_id, type=typetrans, symbol=symbol, shares=shares, price=price)

    newCash = cash - cost
    db.execute("UPDATE users SET cash = :newCash WHERE id = :user_id", newCash=newCash, user_id=user_id)

    currshares = db.execute("SELECT shares FROM holdings WHERE user_id = :user_id AND symbol = :symbol", user_id=user_id, symbol=symbol)

    # if this stock never been entered for this person
    if len(currshares) == 0:
        # this is a new stock so add it to portfolio
        db.execute("INSERT INTO holdings('user_id', 'symbol', 'shares') VALUES (:user_id, :symbol, :shares)", user_id=user_id, symbol=symbol, shares=shares)
        #return apology("New add to holdings", 403)
        return redirect(url_for('index'))

    # this stock has an entry for this user so update it
    db.execute("UPDATE holdings SET shares = :shares WHERE user_id = :user_id AND symbol = :symbol", shares=currshares[0]["shares"] + shares, user_id=user_id, symbol=symbol)

    #return apology("Updated holdings", 403)
    return redirect(url_for('index'))

@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""
    username = request.args.get("username")
    if len(username) > 0:
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=username)
    else:
        return jsonify(False)

    # if it's taken return false
    if len(rows) !=0:
        return jsonify(False)
    return jsonify(True)

@app.route("/history")
@login_required # decorated with login_required - function in helpers.py
def history():
    user_id = session['user_id']
    rows = db.execute("SELECT * FROM transactions WHERE userid = :user_id", user_id=session["user_id"])

    table = "<table class='table'><thead><tr><th>Type</th><th>Symbol</th><th>Shares</th><th>Price</th><th>Time</th></tr></thead><tbody>"
    totalValue = 0
    for row in rows:
        symbol = row["symbol"]
        shares = row["shares"]
        price = row["price"]
        transtype = row["type"]
        time = row["time"]

        table = table + "<tr><td>" + transtype + "</td><td>" + symbol + "</td><td>" + str(shares) + "</td><td>" + str(usd(price)) + "</td><td>" + str(time) + "</td></tr>"

    table = table + "</tbody><tfoot></tfoot></table>"
    return render_template("history.html", table=table)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]


        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    # quote.html takes symbol user wants to look up

    if request.method == 'GET':
        return render_template("quote.html")

    res = ""
    res = lookup(request.form.get("symbol"))
    #print(res)
    if not res:
        return apology("Could not find that symbol")

    symbol = res['symbol']
    name = res['name']
    price = usd(res['price'])
    return render_template("quoted.html", symbol=symbol, price=price, name=name)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    #return apology("TODO")
    session.clear()

    if request.method == "POST":
        if not request.form.get("username"):
            return apology("must provide username", 400)
        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        if len(rows) !=0:
            return apology("Username is taken please choose another", 400)

        if not request.form.get("password") or not request.form.get("confirmation"):
            return apology("Please enter password and confirmation", 400)

        if request.form.get("password") != request.form.get("confirmation"):
            return apology("password must equal confirmation value", 400)

        hash = generate_password_hash(request.form.get("password"))

        result = db.execute("INSERT INTO users('username', 'hash') VALUES (:username, :password)",
            username=request.form.get("username"), password=hash)

        if not result:
            return apology("Something went wrong with your registration. Try another username")

        # Log the user in
        rows = db.execute("SELECT * FROM users WHERE username = :name", name=request.form.get("username"))
        session["user_id"] = rows[0]["id"]
        session["username"] = rows[0]["username"]

        return "Welcome " + session["username"]

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == 'GET':
        rows = db.execute("SELECT * FROM holdings WHERE user_id = :user_id", user_id=session["user_id"])
        rows2 = db.execute("SELECT * FROM users where id = :user_id", user_id=session['user_id'])
        cash = rows2[0]["cash"]

        form = "<form action='/sell' method='post'>"
        form = form + "<div class='form-group'>"
        form = form + "<label for'symbol'>Stock to sell</label> "
        form = form + "<select name='symbol' class='form-control' id='symbol'>"
        for row in rows:
            form = form + "<option>" + row["symbol"] + "</option>"
        form = form + "</select></div>"

        form = form + "<div class='form-group'>"
        form = form + "<input class='form-control' min='1' name='shares' placeholder='# of shares' type='number' required></div>"
        form = form + "<button class='btn btn-primary' type='submit'>Sell</button>"
        form = form + "</form>"
        return render_template("sell.html", form=form)

    # otherwise request is a post request
    shares = int(request.form.get("shares"))
    symbol = request.form.get("symbol")
    user_id = session['user_id']

    currHolding = db.execute("SELECT * FROM holdings WHERE user_id = :user_id AND symbol = :symbol", user_id=user_id, symbol=symbol)
    currUser = db.execute("SELECT * FROM users WHERE id = :user_id", user_id=user_id)
    currShares = int(currHolding[0]["shares"])

    if currShares >= int(shares):
        # user has enough shares to sell
        stock = lookup(symbol)
        currPrice = stock["price"]
        gain = currPrice * int(shares)
        currCash = currUser[0]["cash"]

        db.execute("UPDATE holdings SET shares = :shares WHERE user_id = :user_id AND symbol = :symbol", shares=currShares - shares, user_id=user_id, symbol=symbol)
        db.execute("UPDATE users SET cash = :cash WHERE id = :user_id", cash=currCash + gain, user_id=user_id)

        typetrans = 'sell'
        db.execute("INSERT INTO transactions('userid', 'type', 'symbol', 'shares', 'price') VALUES (:userid, :type, :symbol, :shares, :price)", userid=user_id, type=typetrans, symbol=symbol, shares=shares, price=currPrice)
        return redirect(url_for('index'))

    else:
        return apology("You don't have enough shares!")

    # Check if the user has that many shares of stock


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
