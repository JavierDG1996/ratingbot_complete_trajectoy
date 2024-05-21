from configparser import ConfigParser

file = 'config.ini'
config = ConfigParser()
config.read(file)

def tr(msg, u):

    if msg == 'lang':
        return config['user_lang_question']['lang_question']
    else:
        Exception("Please select a language")

    if msg == "welcome":
        if u.lang == 'en':
            return config['dataset_survey_messages_en']['welcome']
        elif u.lang == 'es':
            return config['dataset_survey_messages_es']['welcome']
        else:
            Exception('Unknown language "'+u.lang+'"')

    if msg == "give_me_score":
        if u.lang == 'en':
            return config['dataset_survey_messages_en']['give_me_score']
        elif u.lang == 'es':
            return config['dataset_survey_messages_es']['give_me_score']
        else:
            Exception('Unknown language "'+u.lang+'"')

    if msg == "notvalid":
        if u.lang == 'en':
            return config['dataset_survey_messages_en']['not_valid']
        elif u.lang == 'es':
            return config['dataset_survey_messages_es']['not_valid']
        else:
            Exception('Unknown language "'+u.lang+'"')

    if msg == "donestill":
        if u.lang == 'en':
            return config['dataset_survey_messages_en']['done_still']
        elif u.lang == 'es':
            return config['dataset_survey_messages_es']['done_still']
        else:
            Exception('Unknown language "'+u.lang+'"')

    if msg == "done":
        if u.lang == 'en':
            return config['dataset_survey_messages_en']['done']
        elif u.lang == 'es':
            return config['dataset_survey_messages_es']['done']
        else:
            Exception('Unknown language "'+u.lang+'"')

    if msg == "cannotdelete":
        if u.lang == 'en':
            return config['dataset_survey_messages_en']['cannot_delete']
        elif u.lang == 'es':
            return config['dataset_survey_messages_es']['cannot_delete']
        else:
            Exception('Unknown language "'+u.lang+'"')


    if msg == "access":
        if u.lang == 'en':
            return config['dataset_survey_messages_en']['access']
        elif u.lang == 'es':
            return config['dataset_survey_messages_es']['access']
        else:
            Exception('Unknown language "'+u.lang+'"')


    if msg == "help":
        if u.lang == 'en':
            return config['dataset_survey_messages_en']['help']
        elif u.lang == 'es':
            return config['dataset_survey_messages_es']['help']
        else:
            Exception('Unknown language "'+u.lang+'"')

    if msg == "backup":
        if u.lang == 'en':
            return config['dataset_survey_messages_en']['backup']
        elif u.lang == 'es':
            return config['dataset_survey_messages_es']['backup']
        else:
            Exception('Unknown language "'+u.lang+'"')

    if msg == "cannot_backup":
        if u.lang == 'en':
            return config['dataset_survey_messages_en']['cannot_backup']
        elif u.lang == 'es':
            return config['dataset_survey_messages_es']['cannot_backup']
        else:
            Exception('Unknown language "'+u.lang+'"')
            
    if msg == "choose_value":
        if u.lang == 'en':
            return config['dataset_survey_messages_en']['choose_value']
        elif u.lang == 'es':
            return config['dataset_survey_messages_es']['choose_value']
        else:
            Exception('Unknown language "'+u.lang+'"')

    if msg == "arigato":
        if u.lang == 'en':
            return config['dataset_survey_messages_en']['arigato']
        elif u.lang == 'es':
            return config['dataset_survey_messages_es']['arigato']
        else:
            Exception('Unknown language "'+u.lang+'"')

    if msg == "syntax":
        if u.lang == 'en':
            return config['dataset_survey_messages_en']['syntax']
        elif u.lang == 'es':
            return config['dataset_survey_messages_es']['syntax']
        else:
            Exception('Unknown language "'+u.lang+'"')
            
    if msg == "sending_sample":
        if u.lang == 'en':
            return config['dataset_survey_messages_en']['sending_sample']
        elif u.lang == 'es':
            return config['dataset_survey_messages_es']['sending_sample']
        else:
            Exception('Unknown language "'+u.lang+'"')
            
    if msg == "ranking_msg_1":
        if u.lang == 'en':
            return config['dataset_survey_messages_en']['ranking_msg_1']
        elif u.lang == 'es':
            return config['dataset_survey_messages_es']['ranking_msg_1']
        else:
            Exception('Unknown language "'+u.lang+'"')
            
    if msg == "ranking_msg_2":
        if u.lang == 'en':
            return config['dataset_survey_messages_en']['ranking_msg_2']
        elif u.lang == 'es':
            return config['dataset_survey_messages_es']['ranking_msg_2']
        else:
            Exception('Unknown language "'+u.lang+'"')
            
    if msg == "video_found":
        if u.lang == 'en':
            return config['dataset_survey_messages_en']['video_found']
        elif u.lang == 'es':
            return config['dataset_survey_messages_es']['video_found']
        else:
            Exception('Unknown language "'+u.lang+'"')

    if msg == "not_video_found":
        if u.lang == 'en':
            return config['dataset_survey_messages_en']['not_video_found']
        elif u.lang == 'es':
            return config['dataset_survey_messages_es']['not_video_found']
        else:
            Exception('Unknown language "'+u.lang+'"')
            
    if msg == "q0question":
        if u.lang == 'en':
            return config['dataset_survey_messages_en']['q0_question']
        elif u.lang == 'es':
            return config['dataset_survey_messages_es']['q0_question']
        else:
            Exception('Unknown language "'+u.lang+'"')


    if msg == "q0confirmation":
        if u.lang == 'en':
            return config['dataset_survey_messages_en']['q0_confirmation']
        elif u.lang == 'es':
            return config['dataset_survey_messages_es']['q0_confirmation']
        else:
            Exception('Unknown language "'+u.lang+'"')
