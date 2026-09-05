#include "widget.h"
#include "ui_widget.h"
#include "message_store.h"
#include "style.h"
#include <QCheckBox>
#include <QBoxLayout>
#include <QDir>
#include <QNetworkInterface>
#include <QFileDialog>
#include <QDebug>
#include <QListWidgetItem>
#include <QColor>
#include <QTableWidget>
#include <QRegularExpression>

Widget::~Widget()
{
    delete ui;
    delete store;
}

void Widget::applyTheme(bool dark)
{
    setStyleSheet(dark ? darkStyleSheet() : lightStyleSheet());
}

// 取本机局域网 IPv4，用于界面展示（绑定仍用 Any，见构造函数）
QHostAddress Widget::get_local_host_ip()
{
    foreach (const QHostAddress &address, QNetworkInterface::allAddresses()) {
        if (address.protocol() == QAbstractSocket::IPv4Protocol &&
            address != QHostAddress::Null &&
            address != QHostAddress::LocalHost &&
            !address.toString().startsWith("127.")) {
            return address;
        }
    }
    return QHostAddress::Any;
}

Widget::Widget(QWidget *parent)
    : QWidget(parent)
    , ui(new Ui::Widget)
    , tcp_thread(nullptr)
    , udp_thread(nullptr)
{
    ui->setupUi(this);
    setWindowTitle("上位机（服务端）");

    // 主题：由“暗色主题”复选框切换；CAR_THEME=dark 环境变量可强制暗色（便于测试）。
    connect(ui->theme_check, &QCheckBox::toggled, this, &Widget::applyTheme);
    bool dark = ui->theme_check->isChecked();
    if (qEnvironmentVariable("CAR_THEME") == "dark") {
        ui->theme_check->setChecked(true);
        dark = true;
    }
    applyTheme(dark);

    // 左右列比例：左（视频+历史）更宽，右（控制台）紧凑固定宽。
    // .ui 里 QHBoxLayout 的两列靠 stretch + 右列最小宽来分配，避免右列被压缩到 0。
    if (QBoxLayout *lay = qobject_cast<QBoxLayout *>(layout())) {
        lay->setStretch(0, 3);   // leftCol
        lay->setStretch(1, 0);   // panel_right
    }
    ui->panel_right->setMinimumWidth(300);

    QString udp_port = "8888";   // 运算端回传视频
    QString tcp_port = "9999";   // 运算端指令/事件

    // 默认保存目录（相对程序运行目录，自动创建）
    ui->lineEdit_path->setText("screenshots/");
    ui->line_ip_addr->setText(get_local_host_ip().toString());
    ui->line_udp_port->setText(udp_port);
    ui->line_tcp_port->setText(tcp_port);
    store = new MessageStore();

    // 监听所有网卡，保证回环(127.0.0.1)与局域网都能连上
    QHostAddress local_ip = QHostAddress::Any;

    tcp_thread = new Tcp_Thread(local_ip, tcp_port);
    connect(tcp_thread, &Tcp_Thread::signal_msg, this, &Widget::print_tcp_msg);

    udp_thread = new Udp_Thread(local_ip, udp_port);
    connect(udp_thread, &Udp_Thread::signal_img, this, &Widget::display_udp_frame);
    connect(udp_thread, &Udp_Thread::signal_img_saved, this, &Widget::on_img_saved);

    connect(this, &Widget::destroyed, this, &Widget::close_thread);

    tcp_thread->start();
    udp_thread->start();
    tcp_thread->stop();
    udp_thread->stop();   // 等点击“开启监听”后再工作
    ui->label_msg->setText("等待客户端连接...");

    store->open();

    connect(ui->selectBtn,   &QPushButton::clicked, this, &Widget::on_selectBtn_clicked);
    connect(ui->deleteButton,&QPushButton::clicked, this, &Widget::on_deleteButton_clicked);
    connect(ui->addButton,   &QPushButton::clicked, this, &Widget::on_addButton_clicked);
    connect(ui->changeButton,&QPushButton::clicked, this, &Widget::on_changeButton_clicked);
    connect(ui->open,        &QPushButton::clicked, this, &Widget::on_open_clicked);
    connect(ui->close,       &QPushButton::clicked, this, &Widget::on_close_clicked);
    connect(ui->openButton,  &QPushButton::clicked, this, &Widget::on_openButton_clicked);
    connect(ui->closeButton, &QPushButton::clicked, this, &Widget::on_closeButton_clicked);
    connect(ui->btn_send,    &QPushButton::clicked, this, &Widget::on_btn_send_clicked);
    connect(ui->btn_path_change, &QPushButton::clicked, this, &Widget::on_btn_path_change_clicked);
}

void Widget::display_udp_frame()
{
    // 取出所有待显示帧（线程安全）
    while (udp_thread->has_frame()) {
        ui->label_frame->setPixmap(udp_thread->take_frame());
    }
    QString saved = udp_thread->take_save_result();
    if (!saved.isEmpty())
        ui->label_msg->append("已保存！" + saved);
}

void Widget::print_tcp_msg()
{
    while (tcp_thread->has_msg()) {
        QString msg = tcp_thread->take_msg();
        ui->label_msg->setTextColor(QColor::fromRgb(255, 0, 0));
        ui->label_msg->append("client: " + msg);
        ui->label_msg->setTextColor(QColor::fromRgb(0, 0, 0));

        // 收到 ID_<id>_start/end 事件 → 触发当前帧保存。
        // 安全：只用数字还原文件名，防止事件串注入路径分割符/`..` 造成任意写文件。
        static const QRegularExpression idRe(QStringLiteral("^ID_(\\d+)_(start|end)$"));
        const QRegularExpressionMatch m = idRe.match(msg);
        if (m.hasMatch()) {
            const QString trackId = m.captured(1);          // 仅取数字 ID
            const QString event = m.captured(2);            // start / end
            const QString current_time = QDateTime::currentDateTime().toString("MM-dd-hh-mm-ss");
            const QString dir = ui->lineEdit_path->text().trimmed();
            const QString file_name = "ID_" + trackId + "_" + event + "_" + current_time + ".jpg";
            const QString file_path = QDir::cleanPath(dir + file_name);
            qDebug() << "Generated file path:" << file_path;
            udp_thread->request_save(file_path);
        }

        if (!tcp_thread->connect_flag) {
            on_btn_open_clicked();
            ui->label_msg->setText("等待客户端连接...");
        }

        // 数据库记录改为记录“保存的图片路径”，见 on_img_saved
    }
}

void Widget::close_thread()
{
    tcp_thread->go_on();
    tcp_thread->start_flag = false;
    tcp_thread->quit();
    tcp_thread->wait();
    if (tcp_thread->connect_flag) {
        tcp_thread->socket->abort();
        tcp_thread->server->close();
    }

    udp_thread->go_on();
    udp_thread->start_flag = false;
    udp_thread->quit();
    udp_thread->wait();
}

void Widget::on_btn_open_clicked()
{
    if (ui->btn_open->text().toUtf8() == "开启监听") {
        if (tcp_thread->connect_flag) {
            ui->btn_open->setText("关闭监听");
            udp_thread->go_on();
            tcp_thread->go_on();
            udp_thread->recv_flag = true;
            tcp_thread->recv_flag = true;
        } else {
            ui->label_msg->append("无客户端连接！");
        }
    } else if (ui->btn_open->text().toUtf8() == "关闭监听") {
        ui->btn_open->setText("开启监听");
        udp_thread->recv_flag = false;
        tcp_thread->recv_flag = false;
        udp_thread->stop();
        tcp_thread->stop();
        ui->label_msg->clear();
        ui->label_frame->clear();
    }
}

void Widget::on_img_saved(const QString &path)
{
    store->storeMessage(path);   // 记录保存的图片路径到数据库
}

void Widget::on_btn_path_change_clicked()
{
    QString dir = QFileDialog::getExistingDirectory(this, "请选择文件保存路径", ".");
    if (dir.isEmpty())
        return;
    ui->lineEdit_path->setText(dir + "/");
    QDir().mkpath(dir);
}

void Widget::on_selectBtn_clicked()
{
    ui->tableWidget->setColumnCount(3);
    ui->tableWidget->setHorizontalHeaderLabels({"ID", "Message", "Timestamp"});
    ui->tableWidget->setRowCount(0);
    ui->tableWidget->verticalHeader()->setVisible(false);

    int row = 0;
    const QList<QSqlRecord> rows = store->all();
    for (const QSqlRecord &rec : rows) {
        ui->tableWidget->insertRow(row);
        ui->tableWidget->setItem(row, 0, new QTableWidgetItem(rec.value("id").toString()));
        ui->tableWidget->setItem(row, 1, new QTableWidgetItem(rec.value("message").toString()));
        ui->tableWidget->setItem(row, 2, new QTableWidgetItem(rec.value("timestamp").toString()));
        row++;
    }
}

void Widget::on_deleteButton_clicked()
{
    QString id = ui->lineEdit1->text().trimmed();
    if (id.isEmpty()) { ui->label_msg->setText("ID is empty!"); return; }

    if (store->removeById(id.toInt()))
        ui->label_msg->setText("Message deleted successfully!");
    else
        ui->label_msg->setText("Error deleting message!");
}

void Widget::on_addButton_clicked()
{
    QString message = ui->lineEdit2->text().trimmed();
    if (message.isEmpty()) { ui->label_msg->setText("Message is empty!"); return; }

    if (store->addMessage(message))
        ui->label_msg->setText("Message inserted successfully!");
    else
        ui->label_msg->setText("Error inserting message!");
    ui->lineEdit2->clear();
}

void Widget::on_changeButton_clicked()
{
    QString id = ui->lineEdit4->text().trimmed();
    QString message = ui->lineEdit3->text().trimmed();
    if (id.isEmpty() || message.isEmpty()) {
        ui->label_msg->setText("ID or Message is empty!");
        return;
    }

    if (store->updateMessage(id.toInt(), message))
        ui->label_msg->setText("Message updated successfully!");
    else
        ui->label_msg->setText("Error updating message!");
    ui->lineEdit3->clear();
    ui->lineEdit4->clear();
}

void Widget::on_open_clicked()       { send_message("0"); }
void Widget::on_close_clicked()      { send_message("1"); }
void Widget::on_openButton_clicked() { send_message("2"); }
void Widget::on_closeButton_clicked(){ send_message("3"); }

void Widget::send_message(const QString &msg)
{
    // 统一以换行结尾（接收端按行分帧）
    if (tcp_thread->connect_flag) {
        tcp_thread->socket->write((msg + "\n").toUtf8());
        tcp_thread->socket->flush();
        ui->label_msg_send->setTextColor(QColor::fromRgb(0, 0, 255));
        ui->label_msg_send->append("server: " + msg);
        ui->label_msg_send->setTextColor(QColor::fromRgb(0, 0, 0));
    } else {
        qDebug() << "Not connected to the client!";
        ui->label_msg->setText("Not connected to the client!");
    }
}

void Widget::on_btn_send_clicked()
{
    QString msg = ui->textEdit_send->toPlainText().trimmed();
    if (!msg.isEmpty() && tcp_thread->socket &&
        tcp_thread->socket->state() == QTcpSocket::ConnectedState) {
        tcp_thread->socket->write((msg + "\n").toUtf8());
        tcp_thread->socket->flush();
        ui->label_msg_send->setTextColor(QColor::fromRgb(0, 0, 255));
        ui->label_msg_send->append("server: " + msg);
        ui->label_msg_send->setTextColor(QColor::fromRgb(0, 0, 0));
        ui->textEdit_send->clear();
    }
}
