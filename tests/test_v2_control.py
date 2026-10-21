import unittest

import v2_control
import grip


class NativeControl(unittest.TestCase):
    def client(self, agent='build', model='model'):
        class Fake:
            state = {'session_id': 's', 'provider_id': 'provider', 'model_id': 'model'}
            calls = []
            def http(self, path, body=None):
                self.calls.append((path,body))
                if path == '/api/session/s': return {'data': {'id':'s','location':{'directory':'/fixture'},
                    'agent':agent,'model':{'id':model,'providerID':'provider'}}}
                if path == '/api/session/active': return {'data': {'s': {'type':'waiting'}}}
                if '/message?' in path:
                    if 'type=user' in path:return {'data':[{'id':'u','type':'user','time':{'created':0},'content':[{'type':'text','text':'latest real user'}]}]}
                    return {'data':[{'id':'a','type':'assistant','agent':'build','finish':'stop','time':{'created':1,'completed':2},'content':[]}]}
                if path.endswith('/prompt'):return {'data':{'id':'actual-inbox-receipt'}}
                raise AssertionError('unknown route: '+path)
        return Fake()

    def test_normalizes_bound_location_and_active_waiting_is_not_idle(self):
        c=self.client()
        self.assertEqual(v2_control.request(c,'/session/s',None)['directory'],'/fixture')
        self.assertEqual(v2_control.request(c,'/session/status',None)['s']['type'],'busy')

    def test_fetches_latest_real_user_even_after_many_tools(self):
        rows=v2_control.request(self.client(),'/session/s/message?limit=32',None)
        self.assertEqual([m['info']['role'] for m in rows],['assistant','user'])
        self.assertEqual(rows[0]['info']['finish'],'stop')

    def test_queues_without_interrupt_switch_or_unpinned_model(self):
        c=self.client()
        result=v2_control.request(c,'/session/s/prompt_async',{'parts':[{'type':'text','text':'continue'}]})
        self.assertEqual(result['id'],'actual-inbox-receipt')
        self.assertEqual(c.calls[-1],('/api/session/s/prompt',{'text':'continue','delivery':'queue'}))
        for agent,model in [('plan','model'),('build','different')]:
            with self.assertRaisesRegex(ValueError,'refuse to override'):
                v2_control.request(self.client(agent,model),'/session/s/prompt_async',{'parts':[{'type':'text','text':'continue'}]})

    def test_never_emulates_native_noReply_or_unsafe_abort(self):
        c=self.client()
        for path,body in [('/session/s/prompt_async',{'noReply':True}),('/session/s/abort',{})]:
            with self.assertRaises(ValueError):v2_control.request(c,path,body)
        self.assertEqual(c.calls,[])

    def test_cancels_only_owned_inbox_and_never_interrupts_human(self):
        class Fake:
            state={'session_id':'s','dispatch_receipt':{'id':'actual-inbox'}}
            calls=[]
            def http(self,path,body=None,method=None):self.calls.append((path,method))
        c=Fake()
        self.assertTrue(v2_control.cancel_pending(c)['cancelled'])
        self.assertEqual(c.calls,[('/api/session/s/inbox/actual-inbox','DELETE')])
        self.assertNotIn('dispatch_receipt',c.state)
        self.assertFalse(v2_control.cancel_pending(c)['cancelled'])

    def test_native_idle_bookkeeping_cannot_hide_completed_turn_or_new_user(self):
        c=self.client();original=c.http
        def http(path,body=None):
            data=original(path,body)
            if '/message?' in path and 'type=user' not in path:
                data['data'].insert(0,{'id':'idle','type':'idle','time':{'created':3},'outcome':'succeeded'})
            return data
        c.http=http
        rows=v2_control.request(c,'/session/s/message?limit=32',None)
        self.assertEqual({m['info']['role'] for m in rows},{'user','assistant'})
        self.assertEqual(max(rows,key=lambda m:m['info']['time']['created'])['info']['finish'],'stop')

    def test_real_native_user_text_preserves_wake_marker_and_human_stop(self):
        row={'id':'u','type':'user','time':{'created':3},'text':grip.MARKER+'\ncontinue current work'}
        self.assertTrue(grip.message_text(v2_control.message(row)).startswith(grip.MARKER))
        row['text']='stop GRIP now'
        user=v2_control.message(row)
        assistant={'info':{'id':'a','role':'assistant','finish':'stop','time':{'created':4,'completed':5}},'parts':[]}
        state={'status':'active','tasks':[{'status':'pending'}]}
        self.assertFalse(grip.eligible(state,{'type':'idle'},[user,assistant]))
        self.assertEqual(grip.message_text(user),'stop GRIP now')


if __name__ == '__main__':unittest.main()
