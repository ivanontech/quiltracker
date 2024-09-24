# quiltracker
 Track Quilibrium node balances live
![image](https://github.com/user-attachments/assets/90d6e615-d490-48fb-8e57-22db24525cc3)
Instructions:
1. Choose / create a host machine to run your dashboard to track all your miners. Input this host IP into the bottom of where 0.0.0.0 is. track_balances.sh. Here -> http://0.0.0.0:5000/update_balance >> $LOG_FILE 2>&1
2. Run: python3 app.py or python app.py
3. sudo ufw allow 5000/tcp on host and miners
4. Put track_balances.sh on all your miners you wish to track
5. Set up a cronjob on your miners to run every minute to grab your node peer ID and balances from track_balances.sh
    1. crontab -e
    2. * * * * * /root/track_balances.sh ![image](https://github.com/user-attachments/assets/70e2eb34-b5bd-4ffb-8804-661c1fd600a0)

6. Visit http://yourip:5000 to access the dashboard.
7. Edit index.html if you wish to add your PEER ID with a local machine name, or delete if you wish
    <li><PeerID:</strong> device name</li>

8. Enjoy, Quil and Chill

               
