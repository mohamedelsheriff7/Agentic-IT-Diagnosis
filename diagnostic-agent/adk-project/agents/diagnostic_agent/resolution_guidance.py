"""User-facing display supplement for the existing backend KB-001 step.

This does not add executable steps, approval, a portal URL or resolution rights.
"""


def step_question(progress, language='en'):
    step = progress['steps'][progress['step_index']]
    if progress.get('article_id') != 'KB-001' or step.get('step_id') != 'PASSWORD_EXPIRED-1':
        return step['instruction'] + ' Have you completed this step? Do not share passwords or verification codes.'
    if language == 'ar':
        return (
            'انتهت صلاحية كلمة المرور. سأرشدك خلال خطوات الخدمة الذاتية.\n\n'
            'عرض تجريبي فقط: لم يُضبط رابط لبوابة كلمات المرور المعتمدة في هذا النموذج. '
            'هذه محاكاة للإجراء ولا تغيّر كلمة مرور حقيقية.\n\n'
            '1. افتح بوابة كلمات المرور المعتمدة باستخدام الرابط الذي يقدمه فريق تقنية المعلومات.\n'
            '2. أكمل أي تحقق مطلوب من هويتك داخل البوابة فقط.\n'
            '3. اتبع تعليمات البوابة لتغيير كلمة المرور بشكل خاص.\n'
            '4. ارجع إلى هذه المحادثة بعد إكمال الخطوات.\n\n'
            'لا ترسل كلمات المرور أو رموز التحقق هنا. '
            'في هذا الاختبار الاصطناعي، يمكنك الرد «تم» لمحاكاة اكتمال الخطوة. '
            'في الاستخدام الفعلي، أكد الاكتمال فقط بعد تنفيذ الإجراء، أو قل «لا» إذا تعذر ذلك.\n\n'
            'هل أكملت هذه الخطوة؟ سأطلب منك بعدها تأكيد نتيجة تسجيل الدخول بشكل منفصل.'
        )
    return (
        "Your password has expired. I’ll guide you through the self-service process.\n\n"
        'Demo only: no approved portal URL is configured in this prototype. '
        'This walkthrough simulates the process; it does not change a real password.\n\n'
        '1. Open the approved password portal using the link provided by your IT team.\n'
        '2. Complete any required identity verification in that portal only.\n'
        '3. Follow the portal instructions to change your password privately.\n'
        '4. Return to this conversation after completing the steps.\n\n'
        'Never share passwords or verification codes here. '
        'For this synthetic demo, reply Done to simulate step completion. '
        'In real use, confirm completion only after performing the procedure, or reply No if you cannot complete it.\n\n'
        'Have you completed this step? I will ask you to confirm the sign-in result separately.'
    )
