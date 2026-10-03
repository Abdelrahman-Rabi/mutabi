'use strict';
// UI copy only. Customer replies, stored drafts, and accounting data are never rewritten.
const arabicCopy = {
  'ChatGPT sign-in timed out. Try connecting again.':'انتهت مهلة تسجيل الدخول. حاول ربط ChatGPT مجددًا.',
  'ChatGPT connection request failed. Try again later.':'تعذر طلب الاتصال بـ ChatGPT. حاول لاحقًا.',
  'Could not contact ChatGPT authorization. Try again later.':'تعذر الاتصال بخدمة تفويض ChatGPT. حاول لاحقًا.',
  'ChatGPT authorization expired or was revoked. Reconnect your account.':'انتهى تفويض ChatGPT أو أُلغي. أعد ربط حسابك.',
  'ChatGPT plan permission is disabled. Reconnect to enable it.':'صلاحية استخدام اشتراك ChatGPT غير مفعّلة. أعد الربط لتفعيلها.',
  'No ChatGPT plan models are available for this account.':'لا توجد نماذج متاحة لاشتراك ChatGPT لهذا الحساب.',
  'Invalid or expired ChatGPT sign-in attempt.':'محاولة تسجيل الدخول غير صالحة أو انتهت مهلتها.',
  'ChatGPT connection was cancelled or permission was declined.':'أُلغي ربط ChatGPT أو رُفض منح الصلاحية.',
  'ChatGPT identity validation failed. Start sign-in again.':'تعذر التحقق من هوية ChatGPT. ابدأ تسجيل الدخول مجددًا.',
  'Disconnected locally. Remote revocation was not confirmed; disconnect Mutabi in ChatGPT settings.':'قُطع الاتصال محليًا. لم يُؤكّد إلغاء التفويض؛ افصل متابع من إعدادات ChatGPT.',
  'AI provider ready':'مزوّد الذكاء الاصطناعي جاهز', 'Connect the selected provider':'اربط المزوّد المحدد',
  'AI provider':'مزوّد الذكاء الاصطناعي', 'ChatGPT plan':'اشتراك ChatGPT', 'Gemini API':'واجهة Gemini API',
  'Continue with ChatGPT':'Continue with ChatGPT', 'Sign-in in progress…':'جارٍ تسجيل الدخول…',
  'Disconnect':'قطع الاتصال', 'Manage usage':'إدارة الاستخدام', 'ChatGPT account':'حساب ChatGPT',
  'Add account':'إضافة حساب', 'Using ChatGPT plan':'يُستخدم اشتراك ChatGPT', 'Plan permission is disabled':'صلاحية استخدام الاشتراك غير مفعّلة',
  'Refresh models':'تحديث النماذج', 'Model':'النموذج', 'Got it':'فهمت',
  'Eligible requests use your ChatGPT plan allowance. Initial sign-in and permission are required.':'تستهلك الطلبات المؤهلة من حدود اشتراك ChatGPT. يلزم تسجيل الدخول والموافقة في البداية.',
  'You’re using your ChatGPT plan. Manage usage in ChatGPT settings.':'تستخدم اشتراك ChatGPT. يمكنك إدارة الاستخدام من إعدادات ChatGPT.',
  'Gemini uses the locally configured API key.':'يستخدم Gemini مفتاح API المعدّ محليًا.',
  'Analyze reply':'تحليل الرد', 'AI interprets · rules validate':'الذكاء الاصطناعي يحلل · القواعد تتحقق',
  'AI is interpreting the reply. The workflow will validate the result before saving changes…':'جارٍ تحليل الرد. سيتحقق النظام من النتيجة قبل حفظ التغييرات…',
  'Synthetic reply saved. Select “Analyze reply” to interpret it.':'حُفظ الرد التجريبي. اختر «تحليل الرد» لمعالجته.',
  'AI provider updated.':'حُدّث مزوّد الذكاء الاصطناعي.', 'ChatGPT settings updated.':'حُدّثت إعدادات ChatGPT.',
  'Complete sign-in and permission in the browser window, then return here.':'أكمل تسجيل الدخول والموافقة في نافذة المتصفح ثم ارجع إلى هنا.',
  'Allow the sign-in popup, then try again.':'اسمح بفتح نافذة تسجيل الدخول ثم أعد المحاولة.',
  'ChatGPT connected. You can analyze a synthetic reply.':'تم ربط ChatGPT. يمكنك تحليل رد تجريبي.',
  'Review the ChatGPT connection and model settings.':'راجع اتصال ChatGPT وإعدادات النموذج.',
  'Connect ChatGPT and enable plan usage.':'اربط ChatGPT وفعّل استخدام الاشتراك.',
  'AI provider settings':'إعدادات مزوّد الذكاء الاصطناعي',
  'Mutabi prototype · AI interprets replies · Accounting and contact channels are simulated':'نموذج متابع · الذكاء الاصطناعي يحلل الردود · النظام المحاسبي وقنوات التواصل تجريبية',
  'Interpretation provider':'مزوّد تحليل الرد',

  'Mutabi home':'الصفحة الرئيسية لمتابع', 'YOUR WORKSPACE':'مساحة العمل',
  '◫   Collections':'◫   التحصيل', 'Keep every':'تابع كل', 'payment promise':'وعد سداد', 'in view.':'بوضوح.',
  'Local demo':'عرض محلي', 'Synthetic data · SAR':'بيانات تجريبية · ر.س',
  'COLLECTIONS WORKSPACE':'مساحة عمل التحصيل', 'Follow up with clarity.':'متابعة واضحة لكل وعد.',
  'Review the reply. Record the promise. Know what comes next.':'راجع الرد، وسجّل وعد السداد، وحدّد الخطوة التالية.',
  'All deliveries are simulated':'جميع عمليات الإرسال تجريبية',
  'Loading…':'جارٍ التحميل…', 'Gemini connected':'Gemini جاهز', 'Gemini key needed':'يلزم إعداد مفتاح Gemini',
  'Workspace summary':'ملخص مساحة العمل', 'Outstanding balance':'الرصيد المستحق',
  'Open promises':'وعود السداد القائمة', 'Commitments awaiting payment':'التزامات بانتظار السداد',
  'Tasks due':'المهام المستحقة', 'Pending tasks as of the demo date':'مهام قائمة حتى تاريخ العرض',
  'Awaiting approval':'بانتظار الموافقة', 'Employee review before sending':'مراجعة الموظف قبل الإرسال',
  'DEMO CLOCK':'تاريخ العرض', 'Demo date':'تاريخ العرض', 'Set date':'تحديث التاريخ', 'Riyadh':'الرياض',
  'Reset demo workspace':'إعادة ضبط العرض', 'Customer cases':'حالات العملاء', 'Search cases':'البحث في الحالات',
  'Search customer or invoice…':'ابحث باسم العميل أو رقم الفاتورة…', 'Loading your workspace…':'جارٍ تحميل مساحة العمل…',
  'Mutabi prototype · Gemini interprets replies · Accounting and contact channels are simulated':'نموذج متابع · Gemini يحلل الردود · النظام المحاسبي وقنوات التواصل تجريبية',
  'Start a fresh demo?':'بدء عرض جديد؟',
  'This clears promises, drafts, approvals, and history in this synthetic workspace and restores the original examples.':'سيؤدي ذلك إلى مسح الوعود والمسودات والموافقات والسجل في مساحة العرض التجريبية واستعادة الأمثلة الأصلية.',
  'Keep workspace':'الاحتفاظ بالبيانات', 'Reset demo':'إعادة ضبط العرض',
  'Settled':'تم السداد', 'Disputed':'فاتورة محل اعتراض', 'Verify payment':'التحقق من السداد',
  'Missed promise':'وعد غير منفّذ', 'Part paid':'سداد جزئي', 'Promise recorded':'وعد مسجّل',
  'Needs details':'يلزم توضيح', 'Needs review':'يلزم مراجعة', 'Overdue':'متأخر',
  'Unassigned replies':'ردود دون فاتورة محددة', 'Needs reference':'يلزم رقم الفاتورة', 'Customer inbox':'رسائل العملاء',
  'CUSTOMER INBOX':'رسائل العملاء', 'Identify the invoice first.':'حدّد الفاتورة أولًا.',
  'An amount match alone is not enough to assign a payment promise.':'تطابق المبلغ وحده لا يكفي لربط وعد السداد بفاتورة.',
  'Process with Gemini':'تحليل الرد باستخدام Gemini', 'View saved result':'عرض النتيجة المحفوظة',
  'pending':'بانتظار التنفيذ', 'processed':'تمت المعالجة', 'Pending':'بانتظار التنفيذ', 'Processed':'تمت المعالجة',
  'CUSTOMER ACCOUNT':'حساب العميل', 'Invoice due':'استحقاق الفاتورة', 'Last balance snapshot':'آخر تحديث للرصيد',
  'Contact channel':'قناة التواصل', 'Simulated inbox':'صندوق رسائل تجريبي',
  'Accounting simulation':'محاكاة النظام المحاسبي', 'Current snapshot only':'الرصيد الحالي فقط',
  'Verify balance':'التحقق من الرصيد', 'Run due follow-ups':'تنفيذ المتابعات المستحقة',
  'Choose an accounting event to test settlement or a missed payment.':'اختر حدثًا محاسبيًا لاختبار السداد أو عدم الالتزام بالوعد.',
  'Uses the existing snapshot. Future events are not applied automatically.':'يُستخدم الرصيد الحالي. لا تُطبّق الأحداث المستقبلية تلقائيًا.',
  'Payment claim — no payment confirmed':'ادعاء سداد دون تأكيد', 'Full payment confirmed':'تأكيد السداد الكامل',
  'Partial payment received':'استلام سداد جزئي', 'Missed promise — balance unchanged':'وعد غير منفّذ والرصيد قائم',
  'Accounting source unavailable':'المصدر المحاسبي غير متاح', 'Payment confirmed before sending':'تأكيد السداد قبل الإرسال',
  'Promise date passed — no payment':'انقضاء موعد الوعد دون سداد',
  'Customer replies':'ردود العملاء', 'Gemini interprets · rules validate':'Gemini يحلل · القواعد تتحقق',
  'No incoming reply yet. Add a synthetic reply below.':'لا يوجد رد وارد حتى الآن. أضف ردًا تجريبيًا أدناه.',
  'Add a synthetic customer reply':'إضافة رد تجريبي من العميل', 'New customer reply':'رد جديد من العميل',
  'I will pay SAR 3,000 on October 5, 2026.':'سأسدد ٣٬٠٠٠ ريال سعودي بتاريخ ٥ أكتوبر ٢٠٢٦.',
  'Save reply':'حفظ الرد', 'Saved replies are processed separately so you can review them first.':'تُحلّل الردود المحفوظة بخطوة منفصلة لتتمكن من مراجعتها أولًا.',
  'Payment promises':'وعود السداد', 'No confirmed promise recorded.':'لم يُسجّل وعد سداد مؤكد.',
  'Next actions':'الإجراءات التالية', 'No follow-up task yet.':'لا توجد مهمة متابعة حتى الآن.',
  'Drafts & approval':'المسودات والموافقات', 'Prepare reminder':'إعداد تذكير', 'Approve draft':'الموافقة على المسودة',
  'Send to simulated inbox':'الإرسال إلى الصندوق التجريبي',
  'Delivered once to the simulated inbox. No customer was contacted.':'أُرسلت الرسالة مرة واحدة إلى الصندوق التجريبي دون التواصل مع عميل حقيقي.',
  'Process a reply or prepare a reminder to create a draft.':'حلّل ردًا أو أعدّ تذكيرًا لإنشاء مسودة.',
  'Your actions will appear here.':'ستظهر الإجراءات هنا.', 'Saved in the workspace':'محفوظ في مساحة العمل',
  'Active':'قائم', 'Fulfilled':'تم الالتزام به', 'Partially fulfilled':'تم الالتزام جزئيًا', 'Missed':'غير منفّذ',
  'Closed':'مغلقة', 'Approved':'معتمدة', 'Sent':'تم الإرسال', 'Invalidated':'لم تعد صالحة للإرسال',
  'Balance check':'مراجعة الرصيد', 'Overdue followup':'متابعة التأخر', 'Payment verification':'التحقق من السداد',
  'Finance review':'مراجعة المالية', 'Human review':'مراجعة الموظف', 'Pending review':'بانتظار المراجعة',
  'Needs human review':'يلزم مراجعة الموظف', 'Needs data review':'يلزم مراجعة البيانات',
  'Awaiting clarification':'بانتظار التوضيح', 'Awaiting payment verification':'بانتظار التحقق من السداد',
  'Dispute pending review':'الاعتراض بانتظار المراجعة', 'Review pending':'بانتظار المراجعة', 'Draft ready':'المسودة جاهزة',
  'Approval required':'تلزم الموافقة', 'Invoice settled':'تم سداد الفاتورة', 'Balance changed review required':'تغيّر الرصيد وتلزم مراجعة المسودة',
  'Dispute review required':'تلزم مراجعة الاعتراض', 'Payment verification pending':'التحقق من السداد لم يكتمل',
  'Contact interval':'لم تنقضِ المدة بين الرسائل', 'Stale balance':'الرصيد غير محدّث', 'Source unavailable':'المصدر غير متاح',
  'Promise recorded. A balance check has been scheduled for the day after the promised date.':'سُجّل وعد السداد، وجُدولت مراجعة الرصيد في اليوم التالي للموعد الموعود.',
  'More detail is needed. Review the clarification draft before approving.':'يلزم مزيد من التفاصيل. راجع مسودة طلب التوضيح قبل الموافقة.',
  'Which invoice does this payment concern?':'ما الفاتورة التي تخص هذا السداد؟',
  'Payment claim recorded. Finance verification is needed; the balance remains authoritative.':'سُجّل ادعاء السداد. يلزم التحقق من المالية، ويظل الرصيد المحاسبي هو المرجع.',
  'Dispute recorded and routed to finance review. The balance has not been reduced.':'سُجّل الاعتراض وأُحيل إلى المالية دون تخفيض الرصيد.',
  'Message delivered to the simulated inbox. No real customer was contacted.':'أُرسلت الرسالة إلى الصندوق التجريبي دون التواصل مع عميل حقيقي.',
  'No balance-check tasks are due for this case on the selected date.':'لا توجد مهام مراجعة رصيد مستحقة لهذه الحالة في التاريخ المحدد.',
  'Draft approved by the demo employee. Sending remains a separate action.':'وافق موظف العرض على المسودة. الإرسال خطوة منفصلة.',
  'Synthetic reply saved. Select “Process with Gemini” to interpret it.':'حُفظ الرد التجريبي. اختر «تحليل الرد باستخدام Gemini» لمعالجته.',
  'Demo date updated. Run follow-ups to check commitments due by this date.':'حُدّث تاريخ العرض. نفّذ المتابعات لمراجعة الالتزامات المستحقة حتى هذا التاريخ.',
  'Demo workspace reset to the original synthetic examples.':'أُعيدت مساحة العرض إلى الأمثلة التجريبية الأصلية.',
  'Reminder draft created for employee review.':'أُنشئت مسودة تذكير لمراجعة الموظف.', 'Action completed.':'اكتمل الإجراء.',
  'Gemini is interpreting the reply. The workflow will validate the result before saving changes…':'Gemini يحلل الرد. سيتحقق النظام من النتيجة قبل حفظ التغييرات…',
  'Updating the workspace…':'جارٍ تحديث مساحة العمل…', 'Could not load workspace':'تعذّر تحميل مساحة العمل',
  'Set GEMINI_API_KEY locally and restart the server.':'أعدّ مفتاح GEMINI_API_KEY محليًا ثم أعد تشغيل الخادم.',
  'Demo time can only move forward. Reset to return to the baseline.':'يمكن تقديم تاريخ العرض فقط. أعد ضبط العرض للعودة إلى التاريخ الأصلي.',
  'Enter a reply containing 1–12000 characters':'أدخل ردًا يتراوح طوله بين حرف واحد و١٢٬٠٠٠ حرف.',
  'Gemini request failed or timed out. No interpretation was saved.':'تعذّر الاتصال بـGemini أو انتهت المهلة. لم يُحفظ تحليل للرد.',
  'Gemini did not return a complete interpretation. Retry or request employee review.':'لم يُرجع Gemini تحليلًا مكتملًا. أعد المحاولة أو اطلب مراجعة الموظف.',
  'Gemini returned invalid or unsupported extraction data. No interpretation was saved.':'أعاد Gemini بيانات غير صالحة أو غير مدعومة. لم يُحفظ تحليل للرد.',
  'Set GEMINI_API_KEY locally to enable live Gemini interpretation.':'أعدّ مفتاح GEMINI_API_KEY محليًا لتفعيل تحليل Gemini.',
  'The action could not be completed. Refresh and review the saved history before retrying.':'تعذّر إكمال الإجراء. حدّث الصفحة وراجع السجل المحفوظ قبل إعادة المحاولة.',
  'Message interpreted':'تم تحليل الرد', 'Message completed':'اكتملت معالجة الرد', 'Promise recorded':'وعد مسجّل',
  'Task created':'أُنشئت المهمة', 'Draft created':'أُنشئت المسودة', 'Draft approved':'اعتُمدت المسودة',
  'Balance verified':'تم التحقق من الرصيد', 'Balance verification failed':'تعذّر التحقق من الرصيد',
  'Followup started':'بدأت المتابعة', 'Followup completed':'اكتملت المتابعة', 'Dispute recorded':'سُجّل الاعتراض',
  'Human review requested':'طُلبت مراجعة الموظف', 'Send blocked':'مُنع الإرسال', 'Simulated delivery':'إرسال تجريبي',
};
let language = localStorage.getItem('mutabi-language') === 'ar' ? 'ar' : 'en';
const staticOriginals = new WeakMap();
function translateCopy(text){
  if(language!=='ar') return text;
  const trimmed=text.trim();if(arabicCopy[trimmed])return text.replace(trimmed,arabicCopy[trimmed]);
  const patterns=[
    [/^Across (\d+) synthetic invoices$/,m=>`عبر ${m[1]} فاتورة تجريبية`],
    [/^SAR (.+)$/,m=>`${m[1]} ر.س`], [/^Riyadh · (.+)$/,m=>`الرياض · ${m[1]}`],
    [/^(.+) · CUSTOMER ACCOUNT$/,m=>`${m[1]} · حساب العميل`],
    [/^(\d+) reply$/,m=>`${m[1]} رد`], [/^Promised for (.+)$/,m=>`موعد السداد: ${m[1]}`],
    [/^Activity history · (\d+) events$/,m=>`سجل الإجراءات · ${m[1]} حدث`],
    [/^Promise date (.+)$/,m=>`موعد الوعد: ${m[1]}`],
    [/^Synthetic event available from (.+) at (.+) Riyadh time\.$/,m=>`الحدث التجريبي متاح من ${m[1]} الساعة ${m[2]} بتوقيت الرياض.`],
    [/^Configured model: (.+)\. Calls require API availability\.$/,m=>`النموذج المعدّ: ${m[1]}. يلزم توفر خدمة API لإجراء الاتصال.`],
    [/^Balance verified: SAR (.+)\.$/,m=>`تم التحقق من الرصيد: ${m[1]} ر.س.`],
    [/^Sending blocked: (.+)\.$/,m=>`مُنع الإرسال: ${translateCopy(m[1])}.`],
    [/^Verification unavailable: (.+)\. No payment confirmation was assumed\.$/,m=>`تعذّر التحقق: ${translateCopy(m[1])}. لم يُفترض تأكيد السداد.`],
    [/^(.+)\. Review the case history for details\.$/,m=>`${translateCopy(m[1])}. راجع سجل الحالة للتفاصيل.`],
    [/^(.+)\. Review the updated tasks and drafts\.$/,m=>`${m[1].split(' · ').map(translateCopy).join(' · ')}. راجع المهام والمسودات المحدّثة.`],
    [/^(.+)\. Review the case before contacting the customer\.$/,m=>`${translateCopy(m[1])}. راجع الحالة قبل التواصل مع العميل.`],
    [/^Gemini API returned HTTP (\d+)\. (.+)$/,m=>`أعادت خدمة Gemini الرمز ${m[1]}. ${m[1]==='429'?'تم بلوغ حد الاستخدام. انتظر قبل المحاولة مجددًا.':Number(m[1])>=500?'الخدمة غير متاحة مؤقتًا. أعد المحاولة لاحقًا.':'تحقق من المفتاح وإتاحة النموذج وحدود المشروع.'}`],
    [/^(.+) Retry after about (\d+) seconds\.$/,m=>`${translateCopy(m[1])} أعد المحاولة بعد نحو ${m[2]} ثانية.`],
  ];
  for(const [pattern,convert] of patterns){const match=trimmed.match(pattern);if(match)return convert(match);}
  return text;
}
function localizeDOM(root,remember=false){
  const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
  let node;
  while((node=walker.nextNode())){
    if(node.parentElement.closest('script,style,.message p,.draft-text'))continue;
    if(remember&&!staticOriginals.has(node))staticOriginals.set(node,node.textContent);
    node.textContent=translateCopy(remember?staticOriginals.get(node):node.textContent);
  }
  root.querySelectorAll('[placeholder],[aria-label],[title]').forEach(element=>{
    for(const attribute of ['placeholder','aria-label','title']){
      if(!element.hasAttribute(attribute))continue;
      const key='i18n'+attribute.replace('-','');
      if(remember&&element.dataset[key]===undefined)element.dataset[key]=element.getAttribute(attribute);
      element.setAttribute(attribute,translateCopy(remember?element.dataset[key]:element.getAttribute(attribute)));
    }
  });
}
