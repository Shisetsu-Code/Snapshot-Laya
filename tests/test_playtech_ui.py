import unittest
from snapshot_laya.playtech_ui import filter_playtech_ocr,analyze_playtech_ocr


def line(text,x=100,y=100,w=140,h=25):
    return {'text':text,'rect':{'x':x,'y':y,'width':w,'height':h}}


def scene(*lines):return {'width':1920,'height':1012,'lines':list(lines)}


class PlaytechUITests(unittest.TestCase):
    def test_common_ui_never_reaches_classifier(self):
        class RejectModel:
            def classify(self,c):raise AssertionError(c['model_input'])
        result=analyze_playtech_ocr(scene(*[line(text,y=i*30) for i,text in enumerate(
            ['TOTAL BET','COIN VALUE','BET','BALANCE','WIN','AUTO PLAY','TURBO','INFO','SOUND','PLAYING FOR FUN','SPIN'])]),RejectModel())
        self.assertEqual(result['controls'],[])
        self.assertEqual(len(result['ignored_common']),10)
        self.assertEqual(len(result['support_controls']),1)
        self.assertFalse(result['runtime_hit_targets_verified'])
    def test_target_words_override_common_bet_matching(self):
        result=filter_playtech_ocr(scene(line('EXTRA BET'),line('BUY FEATURE',y=350),line('DOUBLE CHANCE',y=600)))
        self.assertEqual(len(result['controls']),3)
        self.assertFalse(result['ignored_common'])
    def test_split_buy_feature_merges_and_removes_nearby_common_labels(self):
        result=filter_playtech_ocr(scene(line('BUY',y=300),line('FEATURE',y=335),line('TOTAL BET',x=120,y=380)))
        self.assertEqual(len(result['controls']),1)
        m=result['controls'][0]['model_input']
        self.assertEqual(m['name'],'BUY FEATURE')
        self.assertNotIn('TOTAL BET',m['labels'])
    def test_unknown_ocr_is_preserved_and_can_explain_toggle(self):
        result=filter_playtech_ocr(scene(line('Fxmn-Btr',y=410),line('HIGHER CHANCE',y=520),line('TO TRIGGER BONUS',y=540),line('OFF',y=585)))
        self.assertEqual(len(result['controls']),1)
        self.assertIn('Fxmn-Btr',result['controls'][0]['model_input']['labels'])
        self.assertIn('OFF',result['controls'][0]['model_input']['labels'])
        self.assertTrue(any(x['text']=='Fxmn-Btr' for x in result['unclassified']))
    def test_confirm_cancel_and_continue_survive_any_position(self):
        result=filter_playtech_ocr(scene(line('CONFIRM',x=1700,y=900),line('CANCEL',x=20,y=900),line('CLICK ANYWHERE TO CONTINUE',x=100,y=10)))
        self.assertEqual(len(result['controls']),3)
        self.assertTrue(all(c['click_target_verified'] is False for c in result['controls']))
    def test_decorative_bonus_is_not_assumed_to_be_button(self):
        result=filter_playtech_ocr(scene(line('BONUS'),line('FREE GAMES',x=1400)))
        self.assertFalse(result['controls'])
        self.assertEqual(len(result['unclassified']),2)
    def test_unseen_text_is_not_silently_called_common_interface(self):
        result=filter_playtech_ocr(scene(line('MYSTERY MODE')))
        self.assertFalse(result['ignored_common'])
        self.assertEqual(result['unclassified'][0]['text'],'MYSTERY MODE')
    def test_invalid_geometry_and_oversized_input_are_rejected(self):
        with self.assertRaises(ValueError):filter_playtech_ocr(scene(line('BUY',x=float('nan'))))
        with self.assertRaises(ValueError):filter_playtech_ocr(scene(*[line('BUY') for _ in range(501)]))
    def test_large_batch_does_not_invoke_gpu_before_rejection(self):
        class RejectModel:
            def classify(self,c):raise AssertionError('Classifier must not run before input validation')
        with self.assertRaises(ValueError):
            analyze_playtech_ocr(scene(*[line('CONFIRM',x=(i%10)*180,y=(i//10)*80) for i in range(33)]),RejectModel())
