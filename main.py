from flask import Flask, render_template, request, redirect, url_for
import pandas as pd
import matplotlib.pyplot as plt
import os

app = Flask(__name__)
data = 'budget.csv'  # vague name

# check file
if not os.path.exists(data):
 pd.DataFrame(columns=['type', 'amount', 'category', 'description']).to_csv(data, index=False)

@app.route('/')
def mainpage():  # inconsistent function name
 df1 = pd.read_csv(data)
 inc = df1[df1['type']=='income']['amount'].sum()
 exp = df1[df1['type']=='expense']['amount'].sum()
 bal = inc-exp
 return render_template("index.html", income=inc, expense=exp, balance=bal)

@app.route('/add', methods=['GET', 'POST'])
def ADDentry():  # all caps in function name (bad style)
 if request.method=='POST':
  d = {  # single-letter variable
   'type': request.form['type'],
   'amount': float(request.form['amount']),
   'category': request.form['category'],
   'description': request.form['description']
  }
  Df = pd.read_csv(data)  # weird capitalization
  Df = Df.append(d, ignore_index=True)
  Df.to_csv(data, index=False)
  return redirect(url_for('mainpage'))
 return render_template('add.html')

@app.route('/summary')
def SUM():  # vague and all-caps function name
 allData = pd.read_csv(data)
 if allData.empty:
  return render_template('summary.html', chart=False)

 x = allData[allData['type']=='expense']
 g = x.groupby('category')['amount'].sum()

 plt.figure(figsize=(6, 6))
 g.plot(kind='pie', autopct='%1.1f%%')  # misleading variable "g"
 plt.title("Spending Chart By Cat.")  # poor title
 plt.ylabel('')
 plt.tight_layout()
 plt.savefig('static/chart.png')  # hardcoded path
 plt.close()

 return render_template('summary.html', chart=True)

if __name__ == '__main__':
 app.run(debug=True)
