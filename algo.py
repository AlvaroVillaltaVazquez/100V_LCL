rshunt = 0.022
ilim = float( input("Valor de limitación de corriente: "))
histeresis = float(input("Porcentaje superior de limitación: "))
vsense = ilim*rshunt*25


print(f"vsense = {vsense}" )
print(f"Limite superior de histéresis = {ilim+ilim * float(histeresis)/100}")



RTOP = vIN/VOUT RDOWN