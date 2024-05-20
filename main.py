import logging
import pickle
import random
import time
import sys, os
import threading
import telegram
import re
from emoji import emojize
from telegram import Update
import numpy as np
import requests
from telegram.ext import CommandHandler, Filters, MessageHandler, Updater, CallbackContext
from ibm_watson import SpeechToTextV1
from ibm_watson.websocket import RecognizeCallback, AudioSource
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
from re import search
from datetime import datetime
import shutil
from configparser import ConfigParser

from msg_tr import tr
from user import ChatState, UserInfo

#Setup Config file
file = 'config.ini'
config = ConfigParser()
config.read(file)

#Obtain admin userid data from config
admin_list_count = list(config['admin'])
admins = []
# En admins se encuentra la lista de usuarios administradores.
x = 0
while x < len(admin_list_count):
    admins.append(config['admin']['userid' + str(x + 1)])
    x+= 1
print('ADMINS = ',admins)
#Obtain main_users userid data from config
main_users_list_count = list(config['main_users'])

# En main_users se encuentran los admins y los usuarios no admins considerados principales
main_users = admins
x = 0
while x < len(main_users_list_count):
    main_users.append(config['main_users']['userid' + str(x + 1)])
    x+= 1
print('MAIN USERS = ',main_users)
# Estos son los ratios en los que aparecen los videos según sean basic o main
main_regular_ratio = float(config['ratio']['main_regular_ratio'])
basic_regular_ratio = float(config['ratio']['basic_regular_ratio'])
initial_basic = int(config['ratio']['initial_basic'])
initial_main = int(config['ratio']['initial_main'])

DEBUG = True
# Lista de puntuación
score_data = []
# Id video actual
current_video_id = ''
############################################################################
# obtener los videos de la carpeta de videos
############################################################################
def get_video_files():
    from os import listdir
    from os.path import isfile, join
    #obtain video directory from config
    mypath = config['video_directory']['video_dir']
    onlyfiles = [f for f in listdir(mypath) if isfile(join(mypath, f))]
    from os import walk
    f = []
    for (dirpath, dirnames, filenames) in walk(mypath):
        f.extend([mypath+x for x in filenames if x.endswith('.mp4')])
    return f
    
############################################################################

############################################################################
#Validates string representation of integer is:
#an integer between 0 - 100
#returns integer if valid
def text_to_integer(text_number, number_words={}):
    if not number_words:
        number_units=["zero", "one", "two", "three", "four", "five", "six", "seven", "eight","nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen","sixteen", "seventeen", "eighteen", "nineteen"]
        number_tens=["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
        number_scales=["hundred", "thousand", "million", "billion", "trillion"]
        number_words["and"]=(1, 0)
        for idx, word in enumerate(number_units): number_words[word]=(1, idx)
        for idx, word in enumerate(number_tens): number_words[word]=(1, idx * 10)
        for idx, word in enumerate(number_scales): number_words[word]=(10 ** (idx * 3 or 2), 0)

    current=result=0
    for word in text_number.split():
        if word not in number_words:
            raise Exception("Illegal word: " + word)

        scale, increment=number_words[word]
        current=current*scale+increment
        if scale>100:
            result+=current
            current=0
    return result+current

############################################################################

############################################################################
class MainClass(object):
    def __init__(self):
        super(MainClass).__init__()
        #Cargando la base de datos
        try:
            self.data = self.load_database()
        except:
            print('Can\'t load the database. Creating a new one.')
            self.data = dict()
            self.data['users'] = dict()
            self.data['files'] = dict()
            self.data['files']['regular'] = list()
            self.data['files']['main'] = list()
            self.data['files']['basic'] = list()
            self.scan_command()
            self.setmain(initial_main)
            self.setbasic(initial_basic)

        self.last_save = time.time()

        #print('READ')
        #print('READ')
        #print('USERS:', self.data['users'])
        #print('REGULAR:', self.data['files']['regular'])
        #print('LEN REGULAR:', len(self.data['files']['regular']))
        #print('MAIN:', self.data['files']['main'])
        #print('LEN MAIN:', len(self.data['files']['main']))
        #print('BASIC:', self.data['files']['basic'])
        #print('LEN BASIC:', len(self.data['files']['basic']))
        #print('READ')
        #print('READ')

        #Obtain bot token from config
        token = config['bot']['token']
        
        #Crear el updater el cual reaccionará cada vez que haya un cambio en los mensajes que se envíen por parte del usuario
        self.updater = Updater(token, use_context=True) # REAL

        self.dispatcher = self.updater.dispatcher
        logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

        #Añadir comandos al dispatcher utilizando CommandHandler
        self.dispatcher.add_handler(CommandHandler('start',   self.start))
        self.dispatcher.add_handler(CommandHandler('flush',   self.flush_command))
        self.dispatcher.add_handler(CommandHandler('delete',  self.delete_command))
        self.dispatcher.add_handler(CommandHandler('ignore',  self.ignore_command))
        self.dispatcher.add_handler(CommandHandler('scan',    self.scan_command))
        self.dispatcher.add_handler(CommandHandler('setmain', self.setmain_command))
        self.dispatcher.add_handler(CommandHandler('print',   self.print_command))
        self.dispatcher.add_handler(CommandHandler('len',     self.len_command))
        self.dispatcher.add_handler(CommandHandler('count',   self.count_command))
        self.dispatcher.add_handler(CommandHandler('help',    self.help_command))
        self.dispatcher.add_handler(CommandHandler('backup',    self.user_backup_command))
        self.dispatcher.add_handler(CommandHandler('get',     self.get_command))
        #self.dispatcher.add_handler(CommandHandler('restart', self.restart_command))
        self.dispatcher.add_handler(CommandHandler('ranking', self.ranking_command))
        self.dispatcher.add_handler(CommandHandler('actual_sample', self.actual_sample_command))
        self.dispatcher.add_handler(CommandHandler('send_input', self.send_input_command))
        self.dispatcher.add_handler(CommandHandler('search_video', self.search_video_command))
        self.dispatcher.add_handler(CommandHandler('add_main_user', self.add_main_user_command))
        self.dispatcher.add_handler(CommandHandler('show_main_user', self.show_main_user_command))
        self.dispatcher.add_handler(CommandHandler('getinput_user', self.getinput_user_command))
        #Añadimos los gestores de mensajes usando MessageHandler. Este MessageHandler solo se activará y permitirá cambios o updates, llamando a text_echo, cuando lo digan los filtros (Filters). En este caso, solo permitirá cambios cuando aparezcan mensajes del usuario y que estos no empiecen por comandos.
        self.dispatcher.add_handler(MessageHandler(Filters.text & (~Filters.command), self.text_echo))
        
        #Se crea el keyboard (lang_kb) para elegir idioma usando ReplyKeyboardMarkup.
        self.lang_kb = telegram.ReplyKeyboardMarkup(
            [[telegram.KeyboardButton('english '+emojize(':United_Kingdom:'))], [telegram.KeyboardButton('castellano '+emojize(':Spain:'))]],
            resize_keyboard=True, one_time_keyboard=True)

        #Se crea el keyboard (main_kb) para elegir una escala a la hora de responder a las preguntas usando ReplyKeyboardMarkup.
        self.main_kb = telegram.ReplyKeyboardMarkup(
            [
                [telegram.KeyboardButton('unacceptable - undesirable (0 '+emojize(':enraged_face:')+' - 20 '+emojize(':unamused_face:')+')'), telegram.KeyboardButton('undesirable - acceptable (20 '+emojize(':unamused_face:')+' - 40 '+emojize(':thinking_face:')+')')],
                [telegram.KeyboardButton('acceptable - good (40 '+emojize(':thinking_face:')+' - 60 '+emojize(':relieved_face:')+')'), telegram.KeyboardButton('good - desirable (60 '+emojize(':relieved_face:')+' - 80 '+emojize(':smiling_face_with_heart-eyes:')+')')],
                [telegram.KeyboardButton('desirable - perfect (80 '+emojize(':smiling_face_with_heart-eyes:')+' - 100 '+emojize(':star-struck:')+')')],
            ],
            resize_keyboard=True, one_time_keyboard=True)
            
        #Se crea el keyboard (a_kb) de la primera escala (unacceptable - undesirable) usando ReplyKeyboardMarkup.
        a_kb =  [telegram.KeyboardButton('0 '+emojize(':enraged_face:'))] + [telegram.KeyboardButton(str(x)) for x in range(1, 20)] + [telegram.KeyboardButton('20 '+emojize(':unamused_face:'))] + [telegram.KeyboardButton('<<')]
        a_kb = [ a_kb[0:6], a_kb[6:15], a_kb[15:] ]
        self.a_kb = telegram.ReplyKeyboardMarkup(a_kb, resize_keyboard=True, one_time_keyboard=True)

        #Se crea el keyboard (b_kb) de la segunda escala (undesirable - acceptable) usando ReplyKeyboardMarkup.
        b_kb =  [telegram.KeyboardButton('20 '+emojize(':unamused_face:'))] + [telegram.KeyboardButton(str(x)) for x in range(21, 40)] + [telegram.KeyboardButton('40 '+emojize(':thinking_face:'))] + [telegram.KeyboardButton('<<')]
        b_kb = [ b_kb[0:6], b_kb[6:15], b_kb[15:] ]
        self.b_kb = telegram.ReplyKeyboardMarkup(b_kb, resize_keyboard=True, one_time_keyboard=True)
        
        #Se crea el keyboard (c_kb) de la tercera escala (acceptable - good) usando ReplyKeyboardMarkup.
        c_kb =  [telegram.KeyboardButton('40 '+emojize(':thinking_face:'))] + [telegram.KeyboardButton(str(x)) for x in range(41, 60)] + [telegram.KeyboardButton('60 '+emojize(':relieved_face:'))] + [telegram.KeyboardButton('<<')]
        c_kb = [ c_kb[0:6], c_kb[6:15], c_kb[15:] ]
        self.c_kb = telegram.ReplyKeyboardMarkup(c_kb, resize_keyboard=True, one_time_keyboard=True)
        
        #Se crea el keyboard (d_kb) de la cuarta escala (good - desirable) usando ReplyKeyboardMarkup.
        d_kb =  [telegram.KeyboardButton('60 '+emojize(':relieved_face:'))] + [telegram.KeyboardButton(str(x)) for x in range(61, 80)] + [telegram.KeyboardButton('80 '+emojize(':smiling_face_with_heart-eyes:'))] + [telegram.KeyboardButton('<<')]
        d_kb = [ d_kb[0:6], d_kb[6:15], d_kb[15:] ]
        self.d_kb = telegram.ReplyKeyboardMarkup(d_kb, resize_keyboard=True, one_time_keyboard=True)
        
        #Se crea el keyboard (e_kb) de la quinta escala (desirable - perfect) usando ReplyKeyboardMarkup.
        e_kb =  [telegram.KeyboardButton('80 '+emojize(':smiling_face_with_heart-eyes:'))] + [telegram.KeyboardButton(str(x)) for x in range(81, 100)] + [telegram.KeyboardButton('100 '+emojize(':star-struck:'))] + [telegram.KeyboardButton('<<')]
        e_kb = [ e_kb[0:6], e_kb[6:15], e_kb[15:] ]
        self.e_kb = telegram.ReplyKeyboardMarkup(e_kb, resize_keyboard=True, one_time_keyboard=True)

    # Método que iniciará nuestro bot y que hará dejarlo en escucha
    def idle(self):
        self.updater.start_polling()
        
    def setbasic(self, set_size):
        print('SET BASIC')
        self.data['files']['basic'] = self.data['files']['main'][0:set_size]


#############################################################################################################
#############                         Database                     ##########################################
#############################################################################################################

    # Método para cargar la base de datos
    def load_database(self):
        with open('bot.db', 'rb') as fd:
            return pickle.load(fd)

    # Método para limpiar la base de datos
    def flush_database(self):
        print('Flushing')
        with open('bot.db', 'wb') as fd:
            pickle.dump(self.data, fd)

    # Método para saber si se ha limpiado la base de datos transcurrido un tiempo
    def check_flush(self):
        delta_seconds = time.time() - self.last_save
        if delta_seconds > 3600:
            self.last_save = time.time()
            self.flush_database()
            
########################################################################## FIN Database ########################################


#############################################################################################################
#############                         Comandos                     ##########################################
#############################################################################################################
    # Método del comando /scan --> permite a un administrador, añadir nuevos videos regulares al conjunto
    def scan_command(self, u=None, c=None):
        if u is not None:
            user = self.get_user_data(u)
            if str(user.uid) not in admins:
                self.reply(u, c, tr('access', user))
                return
        # Se obtienen todos los videos de la carpeta videos
        all_files = get_video_files()
        # De los videos, se coge el conjunto de videos nuevos (los que no están en regular)
        new_files = list( set(all_files) - set(self.data['files']['regular']) )
        # Se añaden los nuevos videos al conjunto de videos regulares
        self.data['files']['regular'] += new_files
        # Se ordenan los videos regulares de forma aleatoria
        random.shuffle(self.data['files']['regular'])
        # Se envía el mensaje de la cantidad de videos regulares
        if u is not None:
            self.reply(u, c, str(len(self.data['files']['regular'])))

    # Método del comando /len
    def len_command(self, u, c):
        user = self.get_user_data(u)
        # Si el usuario tiene el estado de UNINITIALISED o EXPECT_LANGUAGE, se le obliga a elegir el idioma
        if user.state == ChatState.UNINITIALISED:
            self.start(u, c)
        elif user.state == ChatState.EXPECT_LANGUAGE:
            self.reply(u, c, tr('lang', user), kb=self.lang_kb)
        # Si el usuario está en otro estado, devuelve el número de vídeos evaluados por el usuario
        else:
            l = len(user)
            self.reply(u, c, str(l))

    # Método del comando /help --> comando que envía ayuda un archivo de explicación a petición del usuario
    def help_command(self, u, c):
        user = self.get_user_data(u)
        # Si el usuario tiene el estado de UNINITIALISED o EXPECT_LANGUAGE, se le obliga a elegir el idioma
        if user.state == ChatState.UNINITIALISED:
            self.start(u, c)
        elif user.state == ChatState.EXPECT_LANGUAGE:
            self.reply(u, c, tr('lang', user), kb=self.lang_kb)
        # Si el usuario está en otro estado, envía la información de ayuda al usuario
        else:
            self.reply(u, c, tr('help', user))

    # Método del comando /restart
    def restart_command(self, u, c):
        user = self.get_user_data(u)
        # Si el usuario tiene el estado de UNINITIALISED o EXPECT_LANGUAGE, se le obliga a elegir el idioma
        if user.state == ChatState.UNINITIALISED:
            self.start(u, c)
        elif user.state == ChatState.EXPECT_LANGUAGE:
            self.reply(u, c, tr('lang', user), kb=self.lang_kb)
        # Si el usuario está en otro estado, envía la información de ayuda al usuario
        else:
            if str(user.uid) not in admins:
                self.reply(u, c, tr('access', user))
                return
            threading.Thread(target=self.shutdown).start()

    def shutdown(self):
        self.updater.stop()
        self.updater.is_idle = False
        time.sleep(1)
        self.flush_database()
        time.sleep(1)
        # os.exit(0)
        os.system('kill -9 %d' % os.getpid())

    # Método del comando /get --> si el usuario es un admin, el bot le enviará la base de datos (bot.db) en un zip
    def get_command(self, u, c):
        user = self.get_user_data(u)
        if str(user.uid) not in admins:
            self.reply(u, c, tr('access', user))
            return

        from zipfile import ZipFile
        self.flush_database()
        with ZipFile('doc.zip','w') as zip:
            for f in ['bot.db']:
                zip.write(f)
        c.bot.send_document(chat_id=u.message.chat_id, document=open('doc.zip', 'rb'))

    # Método del comando /count --> si el usuario es un admin, el bot te envía el número total de vídeos evaluados entre todos los participantes frente al número de vídeos evaluados por el usuario
    def count_command(self, u, c):
        user = self.get_user_data(u)
        if str(user.uid) not in admins:
            self.reply(u, c, tr('access', user))
            return

        l = len(user)
        total = 0
        # Los items son del tipo UserInfo, entonces en k se guarda el uid y en v se guarda el uname (los datos de user)
        # Se va a recorrer la lista de usuarios de la base de datos y se van a sumar todos los vídeos evaluados por cada usuario
        for k, v in self.data['users'].items():
            total += len(v.input)
        # Se envía el total de vídeos evaluados y, entre paréntesis, los evaluados por ti
        self.reply(u, c, str(total)+' ('+str(l)+')')

    # Método del comando /print --> si el usuario es un admin, el bot envía los nombres de todos los participantes y el número de vídeos que han evaluado cada uno
    def print_command(self, u=None, c=None):
        if u is not None:
            user = self.get_user_data(u)
            if str(user.uid) not in admins:
                self.reply(u, c, tr('access', user))
                return

        ret = ''
        # Los items son del tipo UserInfo, entonces en k se guarda el uid y en v se guarda el uname (los datos de user)
        # Se va a recorrer la lista de usuarios de la base de datos y se va a obtener la información de cada uno (su uid, su nombre y el número de vídeos evaluados)
        for k, v in self.data['users'].items():
            ret += str(k) + ' ' + str(self.data['users'][k].uname) + ' ' + str(len(v.input)) + '\n'
        # Se envía el mensaje completo
        self.reply(u, c, ret)

    # Método del comando /setmain --> permite a un administrador añadir videos regulares al conjunto común de los usuarios principales. Debe venir acompañado de un segundo comando (un número entero) que será utilizado como límite de videos que habrá en el conjunto común.
    def setmain_command(self, u, c):
        user = self.get_user_data(u)
        if str(user.uid) not in admins:
            self.reply(u, c, tr('access', user))
            return

        text = u.message.text.split()
        if len(text) != 2:
            self.reply(u, c, tr('syntax', user))
            return

        text = text[1]

        try:
            set_size = int(text)
            self.setmain(set_size)
            self.setbasic(initial_basic)
        except Exception as e:
            s = str(e)
            self.reply(u, c, s)
        self.reply(u, c, tr('done', user))

    def setmain(self, set_size):
        print('SET MAIN = ', set_size)
        random.shuffle(self.data['files']['regular'])
        for i in self.data['files']['regular']:
            if i not in self.data['files']['main']:
                if len(self.data['files']['main']) >= set_size:
                    break
                else:
                    self.data['files']['main'].append(i)
    
    # Método del comando start
    def start(self, u, c):
        print('-----------------------START comenzar-----------------------------')
        
        user = self.get_user_data(u)
        
        #Si el usuario ha elegido comenzar de nuevo y estaba en alguna pregunta, se borra la evaluación incompleta del input del usuario
        if user.state == ChatState.EXPECT_Q0:
            sid = user.current_sample
            try:
                del user.input[sid]
            except:
                pass
        
        user.lang = ''
        user.current_sample = -1
        user.q0 = -1
        user.state = ChatState.EXPECT_LANGUAGE

        self.reply(u, c, tr('lang', user), kb=self.lang_kb)
        print('--------------------START termina----------------------------')

    # Método del comando flush --> si el usuario es un admin, vuelca la información del pickle en la base de datos (dump) y se quita de memoria
    def flush_command(self, u, c):
        user = self.get_user_data(u)
        if str(user.uid) in admins:
            self.flush_database()
            self.reply(u, c, tr('done', user))

    # Método del comando delete--> El usuario puede eliminar un video que quiera de su input solo con aportar el id del video como segundo argumento
    def delete_command(self, u, c):
        user = self.get_user_data(u)
        # Si el usuario tiene el estado de UNINITIALISED o EXPECT_LANGUAGE, se le obliga a elegir el idioma
        if user.state == ChatState.UNINITIALISED:
            self.start(u, c)
        elif user.state == ChatState.EXPECT_LANGUAGE:
            self.reply(u, c, tr('lang', user), kb=self.lang_kb)
        # Si el usuario está en otro estado, puede eliminar el video que quiera de su input solo con aportar el id del video como segundo argumento
        else:
            text = u.message.text.split()
            if len(text) != 2:
                self.reply(u, c, tr('syntax', user))
                return
            sid = u.message.text.split()[1]
            try:
                
                # Si el sid acaba con una D, es un video duplicado
                if sid.endswith('D'):
                    # Se borra el video duplicado del input, el cual se diferencia del original porque acaba con una D
                    del user.input['videos/'+sid[:-1]+'.mp4'+'D']
                    self.reply(u, c, tr('donestill', user))
                    curr_sample = user.current_sample.split('/')[1].split('.')[0]
                    # Si el video que se está borrando es el que se estaba evaluando, se envía un nuevo ejemplo
                    if curr_sample == sid[:-1]:
                        self.send_new_sample(u, c, user)
                        self.send_q0_question(u, c, user)
                        user.state = ChatState.EXPECT_Q0
                else:
                    # Si el id no acabara en D, es un primer video. Y se borra del input
                    del user.input['videos/'+sid+'.mp4']
                    self.reply(u, c, tr('donestill', user))
                    curr_sample = user.current_sample.split('/')[1].split('.')[0]
                    # Si el video que se está borrando es el que se estaba evaluando, se envía un nuevo ejemplo
                    if curr_sample == sid:
                        self.send_new_sample(u, c, user)
                        self.send_q0_question(u, c, user)
                        user.state = ChatState.EXPECT_Q0
                
            except:
                self.reply(u, c, tr('cannotdelete', user))
            self.check_flush()

    # Método del comando ignore --> ignora el vídeo actual y envía otro
    def ignore_command(self, u, c):
        
        user = self.get_user_data(u)
        # Si el usuario tiene el estado de UNINITIALISED o EXPECT_LANGUAGE, se le obliga a elegir el idioma
        if user.state == ChatState.UNINITIALISED:
            self.start(u, c)
        elif user.state == ChatState.EXPECT_LANGUAGE:
            self.reply(u, c, tr('lang', user), kb=self.lang_kb)
        # Si el usuario está en otro estado, elimina el input del vídeo que se estaba evaluando y se envía otro vídeo con las preguntas
        else:
            sid = user.current_sample
            try:
                del user.input[sid]
            except:
                pass
            self.reply(u, c, tr('done', user))
            self.send_new_sample(u, c, user)
            self.send_q0_question(u, c, user)
            user.state = ChatState.EXPECT_Q0
            self.check_flush()

    #Method to send user a message containing their scoring data
    def user_backup_command(self, u, c):
        #retrieve user data
        user = self.get_user_data(u)
        # Si el usuario tiene el estado de UNINITIALISED o EXPECT_LANGUAGE, se le obliga a elegir el idioma
        if user.state == ChatState.UNINITIALISED:
            self.start(u, c)
        elif user.state == ChatState.EXPECT_LANGUAGE:
            self.reply(u, c, tr('lang', user), kb=self.lang_kb)
        # Si el usuario está en otro estado, se envía un archivo de texto con el respaldo de la información evaluada
        else:
            #create user backup file by copying saved user _data_file.txt into a _backup_data_file file.
            user_file = str(user.uid)+"_data_file.txt"
            backup_user_file = str(user.uid)+"_backup_data_file.txt"
            #check that user has inputed scores before sending file.
            if os.path.isfile(user_file):
                shutil.copyfile(user_file, backup_user_file)
                self.reply(u, c, tr('backup', user))
                c.bot.send_document(chat_id=u.message.chat_id, document=open(str(user.uid)+'_backup_data_file.txt', 'rb'))
                os.remove(str(user.uid)+"_backup_data_file.txt")
            else:
                self.reply(u, c, tr('cannot_backup', user))
                
    # Método del comando /ranking --> el usuario podrá ver el estado del ranking, esto se traduce en ver el top 5 de personas en el ranking además de su posición en el mismo
    def ranking_command(self, u=None, c=None):
        # Si el usuario no es nulo
        if u is not None:
            # Se obtienen sus datos
            user = self.get_user_data(u)

            ret = ''
            
            i = 1
        
            # Se crea un diccionario con la información de los usuarios y se ordena en orden descendente de vídeos evaluados de los usuarios
            users_len_videos_sorted = dict(sorted(self.data['users'].items(), key=lambda item:item[1].get_len_videos(), reverse=True))
            
            self.reply(u, c, 'RANKING')
        
            # Se crea un mensaje con la información de los usuarios (su id, su nombre y los vídeos evaluados) en orden descendente de vídeos evaluados completos
            # Cuando haya 5 iteraciones, se sale (para que sea un top 5)
            for k, v in list(users_len_videos_sorted.items())[:5]:
                if i==1:
                    ret += emojize(':1st_place_medal:')
                elif i==2:
                    ret += emojize(':2nd_place_medal:')
                elif i==3:
                    ret += emojize(':3rd_place_medal:')
                else:
                    ret += str(i)
                ret += ' - ' + str(v.uname) + ' - Videos: ' + str(v.get_len_videos()) + '\n'
                i+=1
                
            # Se envía el mensaje completo
            self.reply(u, c, ret)
            # También se envía la posición del usuario en el ranking
            ret_pos = ''
            ret_pos += tr('ranking_msg_1', user)+ ' ' + str(list(users_len_videos_sorted).index(user.uid)+1) + ' ' + tr('ranking_msg_2', user)+' ' + str(len(self.data['users'][user.uid].input)) + ' '
            if list(users_len_videos_sorted).index(user.uid)+1 == 1:
                ret_pos += emojize(':1st_place_medal:')
            elif list(users_len_videos_sorted).index(user.uid)+1 == 2:
                ret_pos += emojize(':2nd_place_medal:')
            elif list(users_len_videos_sorted).index(user.uid)+1 == 3:
                ret_pos += emojize(':3rd_place_medal:')
            
            self.reply(u, c, ret_pos)
        
        
    # Método del comando /actual_sample --> el usuario podrá recuperar el vídeo que estaba evaluando por si no se acordara
    def actual_sample_command(self, u, c):
        
        #retrieve user data
        user = self.get_user_data(u)
        # Si el usuario tiene el estado de UNINITIALISED o EXPECT_LANGUAGE, se le obliga a elegir el idioma
        if user.state == ChatState.UNINITIALISED:
            self.start(u, c)
        elif user.state == ChatState.EXPECT_LANGUAGE:
            self.reply(u, c, tr('lang', user), kb=self.lang_kb)
        # Si el usuario está en otro estado, se recupera el video que estaba evaluando
        else:
            # También se envía de nuevo la pregunta que el usuario está contestando
            self.reply(u, c, tr('sending_sample', user))

            
            if user.current_sample.endswith('D'):
                #video = 'videos/'+sid[:-1]+'.mp4'
                c.bot.send_video(chat_id=u.message.chat_id, video=open(user.current_sample[:-1], 'rb'), supports_streaming=True)
                self.reply(u, c, 'ID: '+str(user.current_sample.split('/')[1].split('.')[0])+'D')
            else:
                #video = 'videos/'+sid+'.mp4'
                c.bot.send_video(chat_id=u.message.chat_id, video=open(user.current_sample, 'rb'), supports_streaming=True)
                self.reply(u, c, 'ID: '+str(user.current_sample.split('/')[1].split('.')[0]))
            
            #c.bot.send_video(chat_id=u.message.chat_id, video=open(user.current_sample, 'rb'), supports_streaming=True)
            #self.reply(u, c, 'ID: '+str(user.current_sample.split('/')[1].split('.')[0]))
            
            if user.state == ChatState.EXPECT_Q0:
                self.send_q0_question(u, c, user)
        
 
    # Método del comando /send_input --> el usuario podrá recuperar la información de videos realizados a través de un documento
    def send_input_command(self, u, c):
        
        #retrieve user data
        user = self.get_user_data(u)
        # Si el usuario tiene el estado de UNINITIALISED o EXPECT_LANGUAGE, se le obliga a elegir el idioma
        if user.state == ChatState.UNINITIALISED:
            self.start(u, c)
        elif user.state == ChatState.EXPECT_LANGUAGE:
            self.reply(u, c, tr('lang', user), kb=self.lang_kb)
        # Si el usuario está en otro estado, se recupera el video que estaba evaluando
        else:
            
            self.reply(u, c, 'INPUT USER: '+str(user.uname)+' ('+str(user.uid)+')')
            # Si el usuario, no ha hecho ningún video aún, se le notificará
            if user.get_len_videos() == 0:
                self.reply(u, c, 'no input yet')
                return
            ret = ''
            i = 1
            # Se va a recorrer la lista de videos puntuados por el usuario y se mostrarán sus puntuaciones y su fecha en la que fue evaluado cada video
            #for k, v in sorted(user.input.items()):
            for k, v in user.input.items():
                if k.endswith('D'):
                    ret += str(i) + '. VIDEO ' + str(k.split('/')[1].split('.')[0]) + 'D' + ' --- DATOS: ' + str(v) + '\n'
                else:
                    ret += str(i) + '. VIDEO ' + str(k.split('/')[1].split('.')[0]) + ' --- DATOS: ' + str(v) + '\n'
                i+=1
            
            # Si el archivo no existe, se crea uno y el input del usuario es escrito en él
            user_file = "send_input_"+str(user.uid)+".txt"
            # Se crea el archivo
            if not os.path.isfile(user_file):
                with open(user_file, 'w+') as file:
                    # Se añade el mensaje al archivo
                    file.write(ret)
                    # Se cierra el flujo
                    file.close()
            else:
                self.reply(u, c, 'Document already exists')
            
            # Se envía el archivo
            c.bot.send_document(chat_id=u.message.chat_id, document=open('send_input_'+str(user.uid)+'.txt', 'rb'))
            # Se elimina el archivo
            os.remove("send_input_"+str(user.uid)+".txt")
            
            
        
    # Método del comando /search_video --> el usuario podrá ver un video determinado buscandolo por su id
    def search_video_command(self, u, c):
        
        #retrieve user data
        user = self.get_user_data(u)
        # Si el usuario tiene el estado de UNINITIALISED o EXPECT_LANGUAGE, se le obliga a elegir el idioma
        if user.state == ChatState.UNINITIALISED:
            self.start(u, c)
        elif user.state == ChatState.EXPECT_LANGUAGE:
            self.reply(u, c, tr('lang', user), kb=self.lang_kb)
        # Si el usuario está en otro estado, se devuelve el video correspondiente al id
        else:
            text = u.message.text.split()
            if len(text) != 2:
                self.reply(u, c, tr('syntax', user))
                return
            sid = u.message.text.split()[1]
            
            if sid.endswith('D'):
                video = 'videos/'+sid[:-1]+'.mp4'
            else:
                video = 'videos/'+sid+'.mp4'
            
            if os.path.isfile(video):
                self.reply(u, c, tr('sending_sample', user))
            
                c.bot.send_video(chat_id=u.message.chat_id, video=open(video, 'rb'), supports_streaming=True)
                self.reply(u, c, tr('video_found', user)+' '+str(sid))
            else:
                self.reply(u, c, tr('not_video_found', user))

    # Método del comando /add_main_user --> un administrador podrá añadir a una persona como evaluador main
    def add_main_user_command(self, u, c):
        
        #retrieve user data
        user = self.get_user_data(u)
        # Se comprueba que el usuario que ha ejecutado el comando sea un administrador
        if str(user.uid) not in admins:
            self.reply(u, c, tr('access', user))
            return
        # Si el usuario tiene el estado de UNINITIALISED o EXPECT_LANGUAGE, se le obliga a elegir el idioma
        if user.state == ChatState.UNINITIALISED:
            self.start(u, c)
        elif user.state == ChatState.EXPECT_LANGUAGE:
            self.reply(u, c, tr('lang', user), kb=self.lang_kb)
        # Si el usuario está en otro estado, si es administrador podrá añadir a un usuario nuevo como evaluador principal
        else:
            text = u.message.text.split()
            if len(text) != 2:
                self.reply(u, c, tr('syntax', user))
                return
            sid = u.message.text.split()[1]
            # Se comprueba que el usuario no sea evaluador main para que no se repita en la lista
            if sid in main_users:
                self.reply(u, c, 'usuario '+str(sid)+' ya estaba añadido a la lista de main users')
                return
            # Se añade al usuario a la lista main_users y se devuelve la lista con sus ids
            main_users.append(sid)
            self.reply(u, c, 'usuario '+str(sid)+' añadido a la lista de main users')
            self.reply(u, c, 'Lista de main users: '+str(main_users))
            
    # Método del comando /show_main_user --> un administrador podrá conocer la lista de ids que son main users
    def show_main_user_command(self, u, c):
        
        #retrieve user data
        user = self.get_user_data(u)
        # Se comprueba que el usuario que ha ejecutado el comando sea un administrador
        if str(user.uid) not in admins:
            self.reply(u, c, tr('access', user))
            return
        # Si el usuario tiene el estado de UNINITIALISED o EXPECT_LANGUAGE, se le obliga a elegir el idioma
        if user.state == ChatState.UNINITIALISED:
            self.start(u, c)
        elif user.state == ChatState.EXPECT_LANGUAGE:
            self.reply(u, c, tr('lang', user), kb=self.lang_kb)
        # Si el usuario está en otro estado, si es administrador podrá conocer la lista de ids que son main users
        else:
            self.reply(u, c, 'Lista de main users: '+str(main_users))


    # Método del comando /getinput_user --> un administrador puede conocer el input de un usuario determinado aportando el id de ese usuario
    def getinput_user_command(self, u, c):
        
        #retrieve user data
        user = self.get_user_data(u)
        # Se comprueba que el usuario que ha ejecutado el comando sea un administrador
        if str(user.uid) not in admins:
            self.reply(u, c, tr('access', user))
            return
        # Si el usuario tiene el estado de UNINITIALISED o EXPECT_LANGUAGE, se le obliga a elegir el idioma
        if user.state == ChatState.UNINITIALISED:
            self.start(u, c)
        elif user.state == ChatState.EXPECT_LANGUAGE:
            self.reply(u, c, tr('lang', user), kb=self.lang_kb)
        # Si el usuario está en otro estado, si es administrador podrá conocer el input de dicho usuario
        else:
            text = u.message.text.split()
            # Se comprueba que hay un segundo argumento
            if len(text) != 2:
                self.reply(u, c, tr('syntax', user))
                return
            # Se obtiene el id del usuario que se necesita el input
            sid = u.message.text.split()[1]
            # Se ve si el usuario existe o no
            try:
                user_ajeno = self.data['users'][int(sid)]
            except Exception:
                self.reply(u, c, 'Error en la recuperación de datos del usuario ajeno. Puede que no exista')
                return
            
            
            
            self.reply(u, c, 'INPUT USER: '+str(user_ajeno.uname)+' ('+str(sid)+')')
            # Si el usuario ajeno, no ha hecho ningún video aún, se le notificará
            if user_ajeno.get_len_videos() == 0:
                self.reply(u, c, 'no input yet')
                return
            ret = ''
            i = 1
            # Se va a recorrer la lista de videos puntuados por el usuario ajeno y se mostrarán sus puntuaciones y la fecha en la que fue evaluado cada video
            #for k, v in sorted(user.input.items()):
            for k, v in user_ajeno.input.items():
                if k.endswith('D'):
                    ret += str(i) + '. VIDEO ' + str(k.split('/')[1].split('.')[0]) + 'D' + ' --- DATOS: ' + str(v) + '\n'
                else:
                    ret += str(i) + '. VIDEO ' + str(k.split('/')[1].split('.')[0]) + ' --- DATOS: ' + str(v) + '\n'
                i+=1
            
            # Si el archivo no existe, se crea uno y el input del usuario es escrito en él
            user_file = "send_input_"+str(sid)+".txt"
            # Se crea el archivo
            if not os.path.isfile(user_file):
                with open(user_file, 'w+') as file:
                    # Se añade el mensaje al archivo
                    file.write(ret)
                    # Se cierra el flujo
                    file.close()
            else:
                self.reply(u, c, 'Document already exists')
            
            # Se envía el archivo
            c.bot.send_document(chat_id=u.message.chat_id, document=open('send_input_'+str(sid)+'.txt', 'rb'))
            # Se elimina el archivo
            os.remove("send_input_"+str(sid)+".txt")
            
            
                    
########################################################################## FIN comandos ########################################

#############################################################################################################
#############         Conseguir cosas del usuario                  ##########################################
#############################################################################################################

    #creates file with user's scoring data
    def file_score_user(self, userid, score_list):
        
        #conditional check if user has any score data
        if score_list == []:
            print("NOT FOUND")
        #If score data exists, file created named as specific user's userid + _data_file.txt
        else:
            #if no file exists, one is created and the user's score_list is written in
            user_file = str(userid)+"_data_file.txt"
            if not os.path.isfile(user_file):
                with open(user_file, 'w+') as file:
                    file.write("%s" % score_list)
                    file.write("\n")
                    file.close()
            else:
                #if file exists, the score_list data is written into it
                with open(user_file, 'a') as file:
                    file.write("%s" % score_list)
                    file.write("\n")
                    file.close()
        


    # Método para obtener los datos del usuario del updater, como su id y su username, y guardarlos en una clase UserInfo
    def get_user_data(self, src):
        
        uname = None
        # Si el tipo que le llega es Update, se obtiene el id y el username del usuario. Si fuera un entero, el uid sería el propio dato. Si no fuera nada de eso, se lanza una excepción
        if type(src) == telegram.update.Update:
            uid   = src['message']['chat']['id']
            uname = src['message']['chat']['username']
            if uname is None:
                uname = src['message']['chat']['first_name'] + ' ' + src['message']['chat']['last_name']
        elif type(src) == int:
            uid = src
        else:
            raise(str(type(src)))

        # Se crea un atributo de tipo UserInfo con la uid y el username obtenidos
        try:
            ret = self.data['users'][uid]
            if ret.uname is None:
                ret.uname = uname
        except Exception:
            ret = UserInfo(uid, uname)
            self.data['users'][uid] = ret
        
        return ret

############################################ FIN conseguir cosas del usuario ########################################

#############################################################################################################
#############                       send_messages                  ##########################################
#############################################################################################################

    # Método que envía un mensaje de respuesta con un determinado mensaje y que configura (o no) un keyboard específico
    def reply(self, u, c, text, kb=None):
        ret = c.bot.send_message(chat_id=u.effective_chat.id, text=text, reply_markup=kb)

    # Método que envía un mensaje de respuesta con un determinado mensaje y que configura (o no) un keyboard específico
    def set_keyboard(self, u, c, text, kb=None):
        ret = c.bot.send_message(chat_id=u.effective_chat.id, text=text, reply_markup=kb)

    # Método que se encarga de enviar la pregunta al usuario
    def send_q0_question(self, u, c, user):
        self.reply(u, c, tr('q0question', user))
        self.reply(u, c, tr('give_me_score', user), kb=self.main_kb)

    # Método que se encarga de enviar la confirmación de la primera pregunta al usuario
    def send_q0_confirmation(self, u, c, user):
        self.reply(u, c, tr('q0confirmation', user)+emojize(':green_circle:')+emojize(':red_circle:')+emojize(':red_circle:')+emojize(':smiling_face_with_smiling_eyes:'))
        
    # Mensaje de gracias
    def send_thanks(self, u, c, user):
        self.reply(u, c, tr('arigato', user)+emojize(':smiling_face:'))
        
    # Mensaje de bienvenida
    def send_welcome(self, u, c, user):
        self.reply(u, c, tr('welcome', user)+emojize(':smiling_face:'))

########################################################################## FIN send_messages ########################################

#############################################################################################################
#############                         MessageHandler Methods                      ##############################
#############################################################################################################

    # Método que gestiona las acciones que se realizarán cuando el usuario envíe un mensaje que no sea un comando
    def text_echo(self, u, c):
        print('-------------------------COMIENZA LLAMADA A TEXT_ECHO-------------------------')
        # Se consigue la infomación del usuario
        user = self.get_user_data(u)
        # Si el usuario se acaba de conectar, estará en estado UNINTIALISED y se creará su usuario para comenzar
        if user.state == ChatState.UNINITIALISED:
            print('--------------TEXT_ECHO STATE UNINITIALISED----------------')
            self.start(u, c)
        # Si el estado es EXPECT_LANGUAGE, se procede a pedirle el idioma al usuario. Una vez configurado, se envía el mensaje de bienvenida, un vídeo de ejemplo y la pregunta. Ahora el estado del usuario pasa a ser EXPECT_Q0
        elif user.state == ChatState.EXPECT_LANGUAGE:
            print('------------TEXT_ECHO STATE EXPECT_LANGUAGE---------------')
            if self.process_language(u, c, user):
                self.send_welcome(u, c, user)
                #El usuario necesitará información para comenzar
                self.reply(u, c, tr('help', user))
                self.send_new_sample(u, c, user)
                self.send_q0_question(u, c, user)
                user.state = ChatState.EXPECT_Q0
            else:
                self.reply(u, c, tr('lang', user), kb=self.lang_kb)
                
        # Si el estado es EXPECT_Q0, se procede a esperar un valor numérico para la pregunta
        elif user.state == ChatState.EXPECT_Q0:
            print('----------------TEXT_ECHO STATE EXPECT_Q0----------------')
            #appends to array to store user survey information. (To be added to the user specific backup file)
            if(len(score_data)==0):
                date_timestamp = datetime.now()
                date_timestamp_format = date_timestamp.strftime("%d/%m/%Y - (%H:%M:%S)")
                video_id = str(user.current_sample.split('/')[1].split('.')[0])
                score_data.append(date_timestamp_format)
                score_data.append(video_id)
                score_data.append(user.uid)
                
            try:
                # Se obtiene el texto enviado por el usuario
                text_return_q0=self.text_process(u)
                # El texto de respuesta a la primera pregunta es procesada en el método process_question
                if self.process_question(u, c, user, text_return_q0):
                    # Si la respuesta es válida, se añade el valor a la lista de datos de puntuación
                    score_data.append('Q0: '+text_return_q0)
                    self.send_q0_confirmation(u, c, user)
                    self.send_thanks(u, c, user)
                    self.send_new_sample(u, c, user)
                    self.send_q0_question(u, c, user)
                    user.state = ChatState.EXPECT_Q0
                else:
                    print('not process_q0')
            except:
                # Si hubiera algún error ( valor que no sea entre 0 y el 100 ) se enviará un mensaje de error
                self.reply(u, c, tr('notvalid', user), kb=self.main_kb)
        else:
            # Si en algún momento el estado del usuario fuera distinto a los anteriores, se entendería como que ha habido algún problema y se reiniciaría el chat.
            c.bot.send_message(chat_id=u.effective_chat.id, text="It seems that the chat is not initialised. We'll restart...")
            self.start(u, c)

        # Tras algunas evaluaciones, la lista de score_data del usuario se guarda en un fichero de respaldo y se vacía
        if(len(score_data)==4):
            self.file_score_user(user.uid, score_data)
            score_data.clear()
        self.check_flush()
        print('-------------------------TERMINA LLAMADA A TEXT_ECHO-------------------------')


######################################## FIN MessageHandler Methods ########################################

#############################################################################################################
#############                         Process Methods                      ##################################
#############################################################################################################

    # Método encargado de configurar el idioma elegido por el usuario. El texto puede detectar inglés o español
    def process_language(self, u, c, user):
        # Se obtiene el mensaje de texto enviado por el usuario que se encuentra en la variable u
        inp = u.message.text.lower().strip()
        if   len([x for x in ['english',   'ingles', 'inglés']                if inp.find(x)!=-1]) > 0:
            user.lang = 'en'
            return True
        elif len([x for x in [ 'spanish', 'espanol', 'español', 'castellano'] if inp.find(x)!=-1]) > 0 :
            user.lang = 'es'
            return True
        else:
            print('__'+inp+'__')
            return False
    
    # Este método sirve para obtener el mensaje de texto enviado por el usuario y obtener la primera palabra. Esto se utiliza en text_echo a la hora de procesar el valor de las preguntas en un rango o en un número
    def text_process(self, u):
        # Se obtiene el mensaje de texto enviado por el usuario que se encuentra en la variable u
        text = u.message.text.lower().strip()
        # Se consigue la primera palabra del mensaje de texto
        first = str(text.split()[0])
        return first

    # Método que procesa los rangos de evaluación si se hubieran pulsado los botones de rango o de <<
    def process_sequence(self, u, c, user, first):
        # Si la primera palabra es unacceptable, se envía el keyboard de rango 0 - 19
        if first == 'unacceptable':
            self.set_keyboard(u, c, tr('choose_value', user), self.a_kb)
            return False
        # Si la primera palabra es undesirable, se envía el keyboard de rango 20 - 39
        elif first == 'undesirable':
            self.set_keyboard(u, c, tr('choose_value', user), self.b_kb)
            return False
        # Si la primera palabra es acceptable, se envía el keyboard de rango 40 - 59
        elif first == 'acceptable':
            self.set_keyboard(u, c, tr('choose_value', user), self.c_kb)
            return False
        # Si la primera palabra es good, se envía el keyboard de rango 60 - 79
        elif first == 'good':
            self.set_keyboard(u, c, tr('choose_value', user), self.d_kb)
            return False
        # Si la primera palabra es desirable, se envía el keyboard de rango 80 - 100
        elif first == 'desirable':
            self.set_keyboard(u, c, tr('choose_value', user), self.e_kb)
            return False
        # Si el usuario pulsa <<, entonces se vuelve al keyboard de elegir el rango. También se vuelve a enviar la pregunta realizada dependiendo del estado user.state
        elif first == '<<':
            if user.state == ChatState.EXPECT_Q0:
                #self.set_keyboard(u, c, tr('q0question', user), self.main_kb)
                self.send_q0_question(u, c, user)        
            return False
        else:
            return True

    # Método que procesa la evaluación de una pregunta
    def process_question(self, u, c, user, first):
        # Se comprueba si la primera palabra es de un rango o de un número. En el primer caso, se sale del método con false.
        if not self.process_sequence(u, c, user, first):
            return False

        if len(first) > 3:
            raise Exception('invalid input '+first)        
        
        # Si es un dato numérico, dependiendo del estado de user.state, se comprueba si el valor está entre 0 y 100. Después se añade el valor al usuario. Si algo falla, se lanza una excepción.
        try:
            if user.state == ChatState.EXPECT_Q0:
                
                q0 = int(first)
                if q0 < 0 or q0 > 100:
                    raise Exception('invalid input '+first)
                user.add_q0_for_current_sequence(q0)
                
        except Exception:
            print('Invalid input ', first)
            raise Exception('invalid input '+first)
        return True

######################################    FIN Process methods    ################################################

#############################################################################################################
#############                         Send Sample Methods                      ##############################
#############################################################################################################

    # Método gestor que se encarga de enviar un nuevo ejemplo
    def send_new_sample(self, u, c, user):
        print('Send new sample')
        self.reply(u, c, tr('sending_sample', user))
        # Si el usuario forma parte de main_users...
        if str(user.uid) in main_users:
            # MAIN USER
            
            # ...es un usuario principal
            # De forma aleatoria, según el rango main_regular_ratio de valor 0.5, puede que se envíe un ejemplo main o un ejemplo regular.
            if random.random() < main_regular_ratio:
                # SUBSET SAMPLE
                
                # Se prueba a intentar enviar un nuevo ejemplo main (para los usuarios main)
                if not self.send_new_sample_main(u, c, user):
                    
                    # Si no diera cierto, se enviará un nuevo mensaje regular
                    self.send_new_sample_regular(u, c, user)
                    
            else:
                # REGULAR SAMPLE
                
                # Se prueba a intentar enviar un nuevo ejemplo regular
                if not self.send_new_sample_regular(u, c, user):
                    
                    # Si no diera cierto, se enviará un nuevo mensaje main
                    self.send_new_sample_main(u, c, user)
        else:
            # Si el usuario no forma parte de main_users...
            # REGULAR USER
            # ...es un usuario normal
            # De forma aleatoria, según el rango basic_regular_ratio de valor 0.5, puede que se envíe un ejemplo basic o un ejemplo regular.
            if random.random() < basic_regular_ratio:
                # SUBSET SAMPLE
                # Se prueba a intentar enviar un nuevo ejemplo basic
                if not self.send_new_sample_basic(u, c, user):
                    # Si no diera cierto, se enviará un nuevo mensaje regular
                    self.send_new_sample_regular(u, c, user)
            else:
                # REGULAR SAMPLE
                # Se prueba a intentar enviar un nuevo ejemplo regular
                if not self.send_new_sample_regular(u, c, user):
                    # Si no diera cierto, se enviará un nuevo mensaje basic
                    self.send_new_sample_basic(u, c, user)

    # Método de envío de ejemplos que se encarga de enviar un nuevo ejemplo del apartado main
    def send_new_sample_main(self, u, c, user):
        found = False
        # Se reordenan aleatoriamente los vídeos del apartado main
        random.shuffle(self.data['files']['main'])
        # Se comprueban todos los vídeos del tipo main
        for sample in self.data['files']['main']:
            # Si el ejemplo no está en el input del usuario, significa que es un vídeo nuevo no evaluado antes por el usuario
            if not sample in user.input:
                # Si se encuentra un video nuevo para el usuario, found tendrá valor true y no se comprobarán más vídeos
                found = True
                break
        # Se valora la bandera found
        if found:
            
            # Si es True, el vídeo es nuevo para el usuario. Eso significa que este ejemplo será el actual para el usuario...
            user.current_sample = sample
            #... y será enviado por el bot
            c.bot.send_video(chat_id=u.message.chat_id, video=open(sample, 'rb'), supports_streaming=True)
            # También se envía el ID del video
            self.reply(u, c, 'ID: '+str(user.current_sample.split('/')[1].split('.')[0]), kb=self.main_kb)
            # El método devuelve True, saliendo del método y enviando un vídeo completamente nuevo para el usuario
            return True
        else:
            
            # Si la bandera found es False, significa que el vídeo enviado ya ha sido evaluado por el usuario al menos una vez. Por tanto, el resultado será gestionado por el método de envío de mensajes duplicados
            return self.send_new_sample_dup(u, c, user)

    # Método de envío de ejemplos que se encarga de enviar ejemplos ya evaluados anteriormente por el usuario
    def send_new_sample_dup(self, u, c, user):
        print('Send new sample DUP')
        found = False
        # Se reordenan aleatoriamente los vídeos del apartado main
        random.shuffle(self.data['files']['main'])
        # Se comprueban todos los vídeos del tipo main
        for sample in self.data['files']['main']:
            # Si el nombre del ejemplo, con subfijo -D, no está en el input del usuario, significa que es un vídeo que se está evaluando por segunda vez
            if not sample+'D' in user.input:
                # Si se dan las condiciones, found tendrá valor true y no se comprobarán más vídeos
                found = True
                break
            

        # Se valora la bandera found
        if found:
            #if DEBUG: self.reply(u, c, 'Sending a dup one!')
            # Si es True, el vídeo se está evaluando por segunda vez para el usuario. Eso significa que este ejemplo (añadiendole una D al final) será el actual para el usuario...
            user.current_sample = sample+'D'
            #... y será enviado por el bot
            c.bot.send_video(chat_id=u.message.chat_id, video=open(sample, 'rb'), supports_streaming=True)
            # También se envía el ID del video
            self.reply(u, c, 'ID: '+str(user.current_sample.split('/')[1].split('.')[0])+'D', kb=self.main_kb)
            # El método devuelve True, saliendo del método y enviando un vídeo repetido por segunda vez para el usuario
        else:
            # Si se hubieran realizado la evaluación de los videos 2 veces cada uno, el resultado devolvería falso para este método
            self.reply(u, c, 'You did all main samples! / ¡Has completado todos los ejemplos principales!')
        return found

    # Método de envío de ejemplos que se encarga de enviar ejemplos catalogados como basic
    def send_new_sample_basic(self, u, c, user):
        print('Send new sample BASIC')
        found = False
        # Se reordenan aleatoriamente los vídeos del apartado basic
        random.shuffle(self.data['files']['basic'])
        # Se comprueban todos los vídeos del tipo basic
        for sample in self.data['files']['basic']:
            # Si el ejemplo no está en el input del usuario, significa que es un vídeo nuevo no evaluado antes por el usuario
            if not sample in user.input:
                # Si se encuentra un video nuevo para el usuario, found tendrá valor true y no se comprobarán más vídeos
                found = True
                break
        # Se valora la bandera found
        if found:
            # Si es True, el vídeo es nuevo para el usuario. Eso significa que este ejemplo será el actual para el usuario...
            user.current_sample = sample
            #... y será enviado por el bot
            c.bot.send_video(chat_id=u.message.chat_id, video=open(sample, 'rb'), supports_streaming=True)
            # También se envía el ID del video
            self.reply(u, c, 'ID: '+str(user.current_sample.split('/')[1].split('.')[0]), kb=self.main_kb)
        else:
            # Si es False, el usuario ha hecho todos los vídeos básicos
            self.reply(u, c, 'You did all basic samples! / ¡Has completado todos los vídeos básicos!', kb=self.main_kb)
        # Si el valor de found es True se habrá enviado un vídeo, si es False no hará nada
        return found

    # Método de envío de ejemplos que se encarga de enviar ejemplos catalogados como regular
    def send_new_sample_regular(self, u, c, user):
        print('Send new sample REGULAR')
        # Se reordenan aleatoriamente los vídeos del apartado regular
        random.shuffle(self.data['files']['regular'])
        found = False
        # Se comprueban todos los vídeos del tipo regular
        for sample in self.data['files']['regular']:
            # Si el ejemplo no está en el input del usuario, significa que es un vídeo nuevo no evaluado antes por el usuario
            if not sample in user.input:
                # Si se encuentra un video nuevo para el usuario, found tendrá valor true y no se comprobarán más vídeos
                found = True
                break

        # Se valora la bandera found
        if found:
            # Si es True, el vídeo es nuevo para el usuario. Eso significa que este ejemplo será el actual para el usuario...
            user.current_sample = sample
            #... y será enviado por el bot
            c.bot.send_video(chat_id=u.message.chat_id, video=open(sample, 'rb'), supports_streaming=True)
            # También se envía el ID del video
            self.reply(u, c, 'ID: '+str(user.current_sample.split('/')[1].split('.')[0]), kb=self.main_kb)
            # El método devuelve True, saliendo del método y enviando un vídeo completamente nuevo para el usuario
        else:
            # Si found es False. El usuario ha realizado la evaluación de todos los videos regulares
            self.reply(u, c, 'You did all regular samples! / ¡Has completado todos los vídeos regulares!', kb=self.main_kb)
        return found

######################################    FIN Process methods    ################################################

if __name__ == '__main__':
    print('------------------MAIN Aquí empieza----------------------')
    main = MainClass()
    print('------------------MAIN Aquí sigue----------------------')
    main.idle()
    print('------------------MAIN Aquí termina----------------------')
