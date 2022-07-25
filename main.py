from flask import Flask, send_file
from flask_restful import Api, Resource, abort, marshal_with, fields, reqparse
from flask_sqlalchemy import SQLAlchemy
import requests
import json
import matplotlib.pyplot as plt
import threading
import schedule
import time
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
import os

app = Flask(__name__)
api = Api(app)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
db = SQLAlchemy(app)

get_args = reqparse.RequestParser()
get_args.add_argument("iso2", type=str, help="ISO2 required", required=True)


class DataModel(db.Model):
    iso2 = db.Column(db.String, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    confirmed = db.Column(db.Integer, nullable=False)
    deaths = db.Column(db.Integer, nullable=False)
    recovered = db.Column(db.Integer, nullable=False)
    active = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f"Data(name = {name}, confiremd = {confirmed}, deaths = {deaths}, recovered = {recovered}, active = {active})"


resource_fields = {
    'iso2': fields.String,
    'name': fields.String,
    'confirmed': fields.Integer,
    'deaths': fields.Integer,
    'recovered': fields.Integer,
    'active': fields.Integer

}


class Data(Resource):
    @marshal_with(resource_fields)
    def get(self):
        args = get_args.parse_args()
        c_iso2 = args["iso2"]
        result = DataModel.query.filter_by(iso2=c_iso2).first()
        if not result:
            abort(404, message="Country not found")
        return result


class GraphReturn(Resource):
    def get(self):
        args = get_args.parse_args()
        c_iso2 = args["iso2"]
        return send_file('./images/{}.png'.format(c_iso2), mimetype='image/png')


api.add_resource(Data, "/country")
api.add_resource(GraphReturn, "/graph")


def updateDatabase():

    print("Updating database ....")

    globalTotal = 0
    globalDeaths = 0
    globalActive = 0
    globalRecovered = 0

    countries = requests.get("https://api.covid19api.com/countries").json()
    countries = sorted(countries, key=lambda c: c["Country"])
    BASE = "https://api.covid19api.com/total/country/"

    for country in countries:
        countries_info = requests.get(BASE + country["Slug"]).json()
        c_iso2 = country["ISO2"]
        l = len(countries_info)

        if(l != 0 and type(countries_info) != dict):
            # print(type(countries_info))
            # print(countries_info)
            try:

                countryName = countries_info[-1]['Country']
                totalConfirmed = countries_info[-1]['Confirmed']
                totalDeaths = countries_info[-1]['Deaths']
                activeCases = countries_info[-1]['Active'] - \
                    countries_info[-2]['Active']
                totalRecovered = totalConfirmed - (activeCases + totalDeaths)

                globalActive += activeCases
                globalDeaths += totalDeaths
                globalRecovered += totalRecovered
                globalTotal += totalConfirmed

            except Exception:
                print("     " + country['Slug'])
                print(countries_info)
                break

            c_data = DataModel.query.filter_by(iso2=c_iso2).first()
            if not c_data:
                c_data = DataModel(iso2=c_iso2, name=countryName, confirmed=totalConfirmed,
                                   deaths=totalDeaths, recovered=totalRecovered, active=activeCases)
                db.session.add(c_data)
            else:
                c_data.name = countryName
                c_data.confirmed = totalConfirmed
                c_data.deaths = totalDeaths
                c_data.recovered = totalRecovered
                c_data.active = activeCases

            createGraphs(countries_info, c_iso2)
            print("Updated " + countryName)
            db.session.commit()

    g_data = DataModel.query.filter_by(iso2='GBL').first()

    if not g_data:
        g_data = DataModel(iso2='GBL', name="Global", confirmed=globalTotal,
                           deaths=globalDeaths, recovered=globalRecovered, active=globalActive)
        db.session.add(g_data)
    else:
        g_data.name = "Global"
        g_data.confirmed = globalTotal
        g_data.deaths = globalDeaths
        g_data.active = globalActive
        g_data.recovered = globalRecovered
    db.session.commit()

    print("Update complete ...")


def createGraphs(countries_info, c_iso2):
    dates = []
    confirmedArray = []
    deathsArray = []
    recoverArray = []
    activeArray = []
    for datewiseInfo in countries_info:
        confirmedArray.append(datewiseInfo['Confirmed'])
        deathsArray.append(datewiseInfo['Deaths'])
        recoverArray.append(datewiseInfo['Recovered'])
        activeArray.append(datewiseInfo['Active'])
        dates.append(datewiseInfo['Date'][:10])

    fig, ax = plt.subplots()
    ax.plot(dates, confirmedArray, label="Confirmed")
    ax.plot(dates, activeArray, label="Active")
    ax.plot(dates, deathsArray, label="Deaths")
    ax.plot(dates, recoverArray, label="Recovered")
    plt.legend()
    # plt.setp(ax.get_xticklabels(), rotation = 90)
    plt.xticks([0, 200, 400, len(dates)-1])
    ax.set(title="Statistics",
           xlabel="Date",
           ylabel="Cases")
    # plt.show()
    plt.savefig('.\images\{}.png'.format(c_iso2), bbox_inches='tight')
    plt.close('all')
    del fig


@app.route('/reset')
def reset():
    db.drop_all()
    db.create_all()
    return "Done"


if __name__ == "__main__":

    db.create_all()

    thread = threading.Thread(target=updateDatabase)
    thread.start()

    scheduler = BackgroundScheduler()
    scheduler.add_job(func=updateDatabase, trigger="interval", days=1)
    scheduler.start()

    app.run(debug=True, use_reloader=False,
            port=os.getenv("PORT"), host="0.0.0.0")
    atexit.register(lambda: scheduler.shutdown())
