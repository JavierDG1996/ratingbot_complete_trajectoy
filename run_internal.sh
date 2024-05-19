while [ 1 ]
do
	kill -9 `ps ax|grep main.py|grep python3|awk {'print $1'}`
	sleep 1
	python3 main.py 
done

